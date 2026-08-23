"""
Automatic schedule generation service
"""
from collections import Counter
from app.models import Teacher, SchoolClass, TeachingAssignment, ScheduleCell, ScheduleSettings, Subject
from app.services.schedule_solver import CpSatScheduleSolver, ResidualGraphSolver
from app.services.session_util import resolve_session
from app.services.validators import ScheduleValidator


class AutoScheduler:
    """
    Service for automatic schedule generation.
    Implements different strategies for scheduling.
    Supports: teacher_room (дети приходят к учителю), class_room (учитель приходит к классу).
    """

    def __init__(self, session=None, school_id=None):
        self.session = resolve_session(session)
        self.school_id = school_id
        self.validator = ScheduleValidator(self.session, school_id=school_id)
        self.graph_solver = ResidualGraphSolver(self._get_classroom_for_cell, session=self.session)
        self.cp_sat_solver = CpSatScheduleSolver(self._get_classroom_for_cell, session=self.session)

    def _settings_for(self, school_level):
        q = self.session.query(ScheduleSettings).filter_by(school_level=school_level)
        if self.school_id is not None:
            q = q.filter_by(school_id=self.school_id)
        return q.first()

    def _scope(self, query, model):
        if self.school_id is not None and hasattr(model, "school_id"):
            return query.filter(model.school_id == self.school_id)
        return query

    def cp_sat_schedule_shift_iter(
        self,
        shift_id: int,
        school_level: str = "elementary",
        time_limit_sec: float = 60.0,
        random_seed: int = 1,
    ):
        """
        CP-SAT: полная пересборка расписания для одной смены (переназначение слотов).
        """
        yield {
            "type": "progress",
            "current": 1,
            "total": 100,
            "message": "CP-SAT: подготовка данных и метрики «до»",
        }
        yield {
            "type": "progress",
            "current": 5,
            "total": 100,
            "message": "CP-SAT: решение (OR-Tools)",
        }
        result = self.cp_sat_solver.solve_shift(
            shift_id=shift_id,
            school_level=school_level,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
        )
        yield {
            "type": "progress",
            "current": 99,
            "total": 100,
            "message": "CP-SAT: запись результатов",
        }
        if result.status in ("ERROR", "MODEL_INVALID"):
            yield {
                "type": "error",
                "message": result.error_message
                or (result.diagnostics[0].get("reason") if result.diagnostics else "Ошибка CP-SAT"),
            }
            return
        done = {
            "type": "done",
            "count": result.placed_count,
            "solver": "cp_sat_mvp",
            "cp_sat_status": result.status,
            "solver_status": result.solver_status,
            "objective": result.objective,
            "wall_time_sec": result.wall_time_sec,
            "metrics_before": result.metrics_before,
            "metrics_after": result.metrics_after,
            "diagnostics": result.diagnostics,
        }
        if result.status in ("INFEASIBLE", "UNKNOWN"):
            done["solver_used"] = False
        else:
            done["solver_used"] = True
        yield done

    def cp_sat_schedule_shift_result(
        self,
        shift_id: int,
        school_level: str = "elementary",
        time_limit_sec: float = 60.0,
        random_seed: int = 1,
    ):
        """Return last done/error payload for CP-SAT shift run."""
        last: dict = {"type": "done", "count": 0}
        for event in self.cp_sat_schedule_shift_iter(
            shift_id, school_level, time_limit_sec, random_seed
        ):
            if event.get("type") in ("done", "error"):
                last = event
        return last

    def _get_teacher_lessons_for_class_day(self, class_id, day):
        """Map teacher_id -> set(lesson_number) for class/day."""
        rows = self.session.query(ScheduleCell).join(TeachingAssignment).filter(
            ScheduleCell.class_id == class_id,
            ScheduleCell.day_of_week == day,
            TeachingAssignment.teacher_id.isnot(None),
        ).all()
        lessons_by_teacher = {}
        for cell in rows:
            tid = cell.assignment.teacher_id
            if tid not in lessons_by_teacher:
                lessons_by_teacher[tid] = set()
            lessons_by_teacher[tid].add(cell.lesson_number)
        return lessons_by_teacher

    def _prioritize_available_for_adjacent(
        self, available, class_id, day, lesson_num
    ):
        """
        Prefer assignments that create adjacent pair for the same teacher+class.
        """
        lessons_by_teacher = self._get_teacher_lessons_for_class_day(class_id, day)

        def score(row):
            assignment, remaining = row
            tid = assignment.teacher_id
            if not tid:
                return (2, -remaining)
            lessons = lessons_by_teacher.get(tid, set())
            # If one lesson already exists today for this teacher in this class,
            # try to place the second one right next to it.
            if len(lessons) == 1:
                only = next(iter(lessons))
                if abs(lesson_num - only) == 1:
                    return (0, -remaining)
            return (1, -remaining)

        return sorted(available, key=score)

    def _ordered_lessons_for_teacher_class_day(self, assignment, day, max_lessons):
        """
        For teacher-ladder: if teacher already has one lesson in this class/day,
        try adjacent lesson first.
        """
        lessons_by_teacher = self._get_teacher_lessons_for_class_day(assignment.class_id, day)
        tid = assignment.teacher_id
        base = list(range(1, max_lessons + 1))
        if not tid:
            return base

        existing = lessons_by_teacher.get(tid, set())
        if len(existing) != 1:
            return base

        anchor = next(iter(existing))
        around = []
        if anchor + 1 <= max_lessons:
            around.append(anchor + 1)
        if anchor - 1 >= 1:
            around.append(anchor - 1)
        rest = [x for x in base if x not in around]
        return around + rest

    def _get_classroom_for_cell(self, assignment, school_level):
        """
        Определяет classroom_id для ячейки расписания.
        Приоритет: 1) предмет с фиксированным кабинетом, 2) групповой урок в началке, 3) сценарий.
        """
        subject = assignment.subject
        teacher = assignment.teacher
        school_class = assignment.school_class
        settings = self._settings_for(school_level)

        # 1. Предмет с фиксированным кабинетом (Информатика, Физкультура, Технология)
        if subject.requires_fixed_classroom:
            return assignment.preferred_classroom_id or subject.default_classroom_id

        # 2. Началка + групповой предмет: дети уходят к учителю
        if (school_level == 'elementary'
            and settings and settings.elementary_group_subjects_leave
            and assignment.group_number is not None
            and teacher and teacher.home_classroom_id):
            return teacher.home_classroom_id

        # 3. Основной сценарий по настройкам уровня
        mode = settings.classroom_mode if settings else 'class_room'
        if mode == 'teacher_room' and teacher:
            return teacher.home_classroom_id
        if mode == 'class_room' and school_class:
            return school_class.home_classroom_id

        # Fallback: preferred из назначения
        return assignment.preferred_classroom_id

    def schedule_by_teacher_ladder(self, teacher_id, school_level='elementary'):
        """
        'Ladder' strategy: fill teacher's schedule sequentially
        to avoid 'windows' (gaps between lessons).
        
        Returns count of scheduled lessons.
        """
        count = 0
        for event in self.schedule_by_teacher_ladder_iter(teacher_id, school_level):
            if event.get('type') == 'done':
                count = event['count']
        return count

    def schedule_by_teacher_ladder_result(self, teacher_id, school_level='elementary'):
        """Return full done-event payload for non-stream routes."""
        done = {'type': 'done', 'count': 0}
        for event in self.schedule_by_teacher_ladder_iter(teacher_id, school_level):
            if event.get('type') == 'done':
                done = event
        return done

    def _shift_bounds(self, assignment):
        """working_days, start_lesson, end_exclusive, max_lessons_per_day for the class shift."""
        sh = assignment.school_class.shift if assignment.school_class and assignment.school_class.shift_id else None
        if sh:
            return sh.working_days, sh.start_lesson, sh.start_lesson + sh.lessons_count, sh.max_lessons_per_day
        return 5, 1, 8, 7

    def _prefer_consecutive_pairs(self, school_level):
        """True when settings allow 2 lessons of a subject per day — place them back-to-back."""
        settings = (
            self._settings_for(school_level)
        )
        max_per = settings.max_lessons_per_subject_per_day if settings else 2
        return max_per >= 2

    def _iter_assignment_slots(self, assignment, working_days, max_lessons):
        """
        Yield (day, lesson) in ladder order.
        Days where this teacher already has exactly one lesson in the class come first
        so the second hour attaches and makes a consecutive pair.
        """
        sh_days, start, end_excl, sh_max = self._shift_bounds(assignment)
        days = [d for d in range(1, working_days + 1) if d <= sh_days]

        def day_priority(day):
            existing = self._get_teacher_lessons_for_class_day(assignment.class_id, day)
            lessons = existing.get(assignment.teacher_id, set()) if assignment.teacher_id else set()
            return 0 if len(lessons) == 1 else 1

        for day in sorted(days, key=day_priority):
            for lesson in self._ordered_lessons_for_teacher_class_day(
                assignment, day, max_lessons
            ):
                if lesson > sh_max or lesson < start or lesson >= end_excl:
                    continue
                yield day, lesson

    def _iter_pair_starts(self, assignment, working_days, max_lessons):
        """
        Yield (day, lesson) starts of a consecutive pair (lesson, lesson+1).
        Prefer aligned doubles 1-2, 3-4, 5-6, then offset 2-3, 4-5.
        Skip days that already have a lesson of this teacher in this class
        (a new pair would exceed 2 or split an unfinished double).
        """
        sh_days, start, end_excl, sh_max = self._shift_bounds(assignment)
        for day in range(1, working_days + 1):
            if day > sh_days:
                continue
            existing = self._get_teacher_lessons_for_class_day(assignment.class_id, day)
            lessons = existing.get(assignment.teacher_id, set()) if assignment.teacher_id else set()
            if lessons:
                continue
            aligned = []
            offset = []
            for lesson in range(start, end_excl - 1):
                if lesson > sh_max or lesson + 1 > sh_max or lesson + 1 >= end_excl:
                    continue
                if (lesson - start) % 2 == 0:
                    aligned.append(lesson)
                else:
                    offset.append(lesson)
            for lesson in aligned + offset:
                yield day, lesson

    def _round_robin_from_queues(self, queues):
        if not queues:
            return []
        out = []
        maxlen = max(len(q) for q in queues)
        for i in range(maxlen):
            for q in queues:
                if i < len(q):
                    out.append(q[i])
        return out

    def _round_robin_hours(self, assignments):
        """Interleave leftover single hours across classes/subjects."""
        queues = []
        for a in assignments:
            remaining = a.remaining_hours
            if remaining > 0:
                queues.append([a] * remaining)
        return self._round_robin_from_queues(queues)

    def _schedule_units(self, assignments, pair_mode):
        """
        Build placement units. In pair mode: doubles first (round-robin across
        classes), then leftover singles. Otherwise only singles.
        """
        if not pair_mode:
            return [('hour', a) for a in self._round_robin_hours(assignments)]
        pair_queues = []
        hour_queues = []
        for a in assignments:
            remaining = a.remaining_hours
            if remaining <= 0:
                continue
            n_pairs = remaining // 2
            n_hours = remaining % 2
            if n_pairs:
                pair_queues.append([a] * n_pairs)
            if n_hours:
                hour_queues.append([a] * n_hours)
        units = [('pair', a) for a in self._round_robin_from_queues(pair_queues)]
        units.extend(('hour', a) for a in self._round_robin_from_queues(hour_queues))
        return units

    def _create_hour_cell(self, assignment, day, lesson, school_level):
        """Create a cell (and complementary subgroup if possible). Returns cell count."""
        classroom_id = self._get_classroom_for_cell(assignment, school_level)
        errors = self.validator.validate_cell(
            assignment=assignment,
            day=day,
            lesson=lesson,
            classroom_id=classroom_id,
        )
        if errors:
            return 0
        cell = ScheduleCell(
            **({'school_id': self.school_id} if self.school_id is not None else {}),
            class_id=assignment.class_id,
            day_of_week=day,
            lesson_number=lesson,
            assignment_id=assignment.id,
            classroom_id=classroom_id,
        )
        self.session.add(cell)
        self.session.flush()
        n = 1
        if assignment.group_number is not None:
            n += self._try_place_complementary_subgroup(
                assignment, day, lesson, school_level
            )
        return n

    def _place_consecutive_pair(self, assignment, day, lesson, school_level):
        """
        Place two back-to-back hours at lesson and lesson+1.
        Rolls back the first hour if the second does not fit.
        """
        before_ids = {
            c.id
            for c in self.session.query(ScheduleCell).filter(
                ScheduleCell.class_id == assignment.class_id,
                ScheduleCell.day_of_week == day,
                ScheduleCell.lesson_number.in_((lesson, lesson + 1)),
            ).all()
        }
        n1 = self._create_hour_cell(assignment, day, lesson, school_level)
        if not n1:
            return 0
        n2 = self._create_hour_cell(assignment, day, lesson + 1, school_level)
        if n2:
            return n1 + n2
        created = [
            c
            for c in self.session.query(ScheduleCell).filter(
                ScheduleCell.class_id == assignment.class_id,
                ScheduleCell.day_of_week == day,
                ScheduleCell.lesson_number.in_((lesson, lesson + 1)),
            ).all()
            if c.id not in before_ids
        ]
        self._delete_cells(created)
        return 0

    def _place_pair_first_fit(
        self, assignment, school_level, working_days, max_lessons
    ):
        """Place one consecutive double in the first valid pair of slots."""
        for day, lesson in self._iter_pair_starts(assignment, working_days, max_lessons):
            n = self._place_consecutive_pair(assignment, day, lesson, school_level)
            if n:
                return n
        return 0

    def _place_one_teacher_hour_first_fit(
        self, assignment, school_level, working_days, max_lessons
    ):
        """
        Поставить один час назначения учителя — первый подходящий слот в неделе.
        Возвращает число созданных ячеек (1 или 2 при подгруппе + комплемент).
        """
        for day, lesson in self._iter_assignment_slots(assignment, working_days, max_lessons):
            n = self._create_hour_cell(assignment, day, lesson, school_level)
            if n:
                return n
        return 0

    def _cells_at_same_slot(self, cell):
        """This cell plus a parallel subgroup in the same class/day/lesson."""
        rows = (
            self.session.query(ScheduleCell)
            .filter(
                ScheduleCell.class_id == cell.class_id,
                ScheduleCell.day_of_week == cell.day_of_week,
                ScheduleCell.lesson_number == cell.lesson_number,
            )
            .all()
        )
        return rows

    def _try_move_cell(self, cell, new_day, new_lesson, school_level):
        """
        Move this teacher's cell (and parallel subgroup cells) to a new slot.
        Returns True on success; leaves the grid unchanged on failure.
        """
        bundle = self._cells_at_same_slot(cell)
        for c in bundle:
            if c.day_of_week == new_day and c.lesson_number == new_lesson:
                return False
            room = self._get_classroom_for_cell(c.assignment, school_level)
            errors = self.validator.validate_cell(
                assignment=c.assignment,
                day=new_day,
                lesson=new_lesson,
                classroom_id=room,
                exclude_cell_id=c.id,
            )
            if errors:
                return False
            dup = (
                self.session.query(ScheduleCell)
                .filter(
                    ScheduleCell.class_id == c.class_id,
                    ScheduleCell.day_of_week == new_day,
                    ScheduleCell.lesson_number == new_lesson,
                    ScheduleCell.assignment_id == c.assignment_id,
                    ScheduleCell.id != c.id,
                )
                .first()
            )
            if dup:
                return False

        for c in bundle:
            c.day_of_week = new_day
            c.lesson_number = new_lesson
            if c.assignment and c.assignment.teacher_id:
                c.classroom_id = self._get_classroom_for_cell(c.assignment, school_level)
        self.session.flush()
        return True

    def _try_place_hour_by_relocating(
        self, assignment, school_level, working_days, max_lessons
    ):
        """
        If the hour has no free slot, try moving this teacher's own lesson out of
        a candidate slot and placing the leftover hour there.
        """
        teacher_id = assignment.teacher_id
        if not teacher_id:
            return 0

        for day, lesson in self._iter_assignment_slots(assignment, working_days, max_lessons):
            n = self._create_hour_cell(assignment, day, lesson, school_level)
            if n:
                return n

            blocker = self.validator.check_teacher_conflict(
                teacher_id, day, lesson, class_id=assignment.class_id
            )
            if (
                blocker is None
                or not blocker.assignment
                or blocker.assignment.teacher_id != teacher_id
            ):
                continue
            if blocker.class_id == assignment.class_id:
                continue
            class_busy = self.validator.check_class_conflict(
                assignment.class_id, day, lesson, assignment.group_number
            )
            if class_busy:
                continue
            if self.validator.check_subject_per_day_limit(assignment, day):
                continue
            if self.validator.check_teacher_class_per_day_limit(assignment, day):
                continue

            blocker_assignment = blocker.assignment
            old_day, old_lesson = blocker.day_of_week, blocker.lesson_number
            for nd, nl in self._iter_assignment_slots(
                blocker_assignment, working_days, max_lessons
            ):
                if nd == old_day and nl == old_lesson:
                    continue
                if not self._try_move_cell(blocker, nd, nl, school_level):
                    continue
                n = self._create_hour_cell(assignment, day, lesson, school_level)
                if n:
                    return n
                self._try_move_cell(blocker, old_day, old_lesson, school_level)

        return 0

    def _delete_cells(self, cells):
        for cell in cells:
            self.session.delete(cell)
        if cells:
            self.session.flush()

    def _place_hours_backtrack(
        self, hours, school_level, working_days, max_lessons,
        pair_mode=False, node_limit=40000,
    ):
        """DFS over slot variants. In pair_mode tries consecutive doubles first."""
        stats = {"nodes": 0, "placed": 0}

        def rec(idx):
            if idx >= len(hours):
                return True
            if stats["nodes"] >= node_limit:
                return False
            stats["nodes"] += 1
            assignment = hours[idx]
            can_pair = (
                pair_mode
                and idx + 1 < len(hours)
                and hours[idx + 1].id == assignment.id
                and assignment.remaining_hours >= 2
            )
            if can_pair:
                for day, lesson in self._iter_pair_starts(
                    assignment, working_days, max_lessons
                ):
                    n = self._place_consecutive_pair(
                        assignment, day, lesson, school_level
                    )
                    if not n:
                        continue
                    stats["placed"] += n
                    if rec(idx + 2):
                        return True
                    stats["placed"] -= n
                    pair_cells = (
                        self.session.query(ScheduleCell)
                        .filter(
                            ScheduleCell.assignment_id == assignment.id,
                            ScheduleCell.day_of_week == day,
                            ScheduleCell.lesson_number.in_((lesson, lesson + 1)),
                        )
                        .all()
                    )
                    self._delete_cells(pair_cells)
            for day, lesson in self._iter_assignment_slots(
                assignment, working_days, max_lessons
            ):
                classroom_id = self._get_classroom_for_cell(assignment, school_level)
                errors = self.validator.validate_cell(
                    assignment=assignment,
                    day=day,
                    lesson=lesson,
                    classroom_id=classroom_id,
                )
                if errors:
                    continue
                before = (
                    self.session.query(ScheduleCell)
                    .filter_by(class_id=assignment.class_id, day_of_week=day, lesson_number=lesson)
                    .all()
                )
                before_ids = {c.id for c in before}
                n = self._create_hour_cell(assignment, day, lesson, school_level)
                if not n:
                    continue
                created = [
                    c
                    for c in self.session.query(ScheduleCell)
                    .filter_by(class_id=assignment.class_id, day_of_week=day, lesson_number=lesson)
                    .all()
                    if c.id not in before_ids
                ]
                stats["placed"] += n
                if rec(idx + 1):
                    return True
                stats["placed"] -= n
                self._delete_cells(created)
            return False

        rec(0)
        return stats["placed"]

    def _repack_teacher_shifts(
        self, teacher_id, assignments, school_level, working_days, max_lessons,
        pair_mode=False,
    ):
        """
        Rebuild this teacher's cells in shifts that still have leftover hours,
        trying consecutive pairs first (when allowed), then DFS variants.
        Returns net newly placed hours (can be 0).
        """
        leftover = [a for a in assignments if a.remaining_hours > 0]
        if not leftover:
            return 0
        shift_ids = {
            a.school_class.shift_id
            for a in leftover
            if a.school_class and a.school_class.shift_id
        }
        if not shift_ids:
            return 0

        pack_assignments = [
            a
            for a in assignments
            if a.school_class and a.school_class.shift_id in shift_ids
        ]
        unplaced_before = sum(a.remaining_hours for a in pack_assignments)
        cells = (
            self.session.query(ScheduleCell)
            .join(TeachingAssignment)
            .join(SchoolClass)
            .filter(
                TeachingAssignment.teacher_id == teacher_id,
                SchoolClass.shift_id.in_(shift_ids),
            )
            .all()
        )
        snapshot = [
            {
                "class_id": c.class_id,
                "day_of_week": c.day_of_week,
                "lesson_number": c.lesson_number,
                "assignment_id": c.assignment_id,
                "classroom_id": c.classroom_id,
            }
            for c in cells
        ]
        self._delete_cells(cells)

        hours = []
        for kind, assignment in self._schedule_units(pack_assignments, pair_mode):
            if kind == 'pair' and assignment.remaining_hours >= 2:
                n = self._place_pair_first_fit(
                    assignment, school_level, working_days, max_lessons
                )
            else:
                n = self._place_one_teacher_hour_first_fit(
                    assignment, school_level, working_days, max_lessons
                )
            if not n:
                hours.append(assignment)
                if kind == 'pair':
                    hours.append(assignment)

        if hours:
            self._place_hours_backtrack(
                hours, school_level, working_days, max_lessons, pair_mode=pair_mode
            )

        unplaced_after = sum(a.remaining_hours for a in pack_assignments)
        if unplaced_after >= unplaced_before:
            rebuilt = (
                self.session.query(ScheduleCell)
                .join(TeachingAssignment)
                .join(SchoolClass)
                .filter(
                    TeachingAssignment.teacher_id == teacher_id,
                    SchoolClass.shift_id.in_(shift_ids),
                )
                .all()
            )
            self._delete_cells(rebuilt)
            for row in snapshot:
                if self.school_id is not None:
                    row = {**row, 'school_id': self.school_id}
                self.session.add(ScheduleCell(**row))
            self.session.flush()
            return 0
        return unplaced_before - unplaced_after

    def schedule_by_teacher_ladder_iter(self, teacher_id, school_level='elementary'):
        """
        То же, что schedule_by_teacher_ladder, но отдаёт события прогресса для потоковой отдачи.
        Если в настройках «2 урока» — сначала ставит сдвоенные уроки подряд, часы
        разных классов чередуются. Если не умещается — перебирает дни и слоты,
        сохраняя приоритет пар.
        """
        aq = self.session.query(TeachingAssignment)\
            .join(SchoolClass)\
            .filter(
                TeachingAssignment.teacher_id == teacher_id,
                SchoolClass.school_level == school_level
            )
        if self.school_id is not None:
            aq = aq.filter(
                TeachingAssignment.school_id == self.school_id,
                SchoolClass.school_id == self.school_id,
            )
        assignments = aq.order_by(SchoolClass.name, TeachingAssignment.id).all()

        working_days = 5
        max_lessons = 7
        for a in assignments:
            sh = a.school_class.shift if a.school_class and a.school_class.shift_id else None
            if sh:
                working_days = max(working_days, sh.working_days)
                max_lessons = max(max_lessons, sh.max_lessons_per_day)

        pair_mode = self._prefer_consecutive_pairs(school_level)

        initial_total = sum(a.remaining_hours for a in assignments)
        if initial_total == 0:
            yield {'type': 'done', 'count': 0}
            return

        scheduled_count = 0
        max_passes = max(30, initial_total)

        for pass_num in range(max_passes):
            units = self._schedule_units(assignments, pair_mode)
            if not units:
                break

            round_placed = 0
            n_slots = len(units)
            for idx, (kind, assignment) in enumerate(units):
                label = 'сдвоенный урок' if kind == 'pair' else assignment.subject.name
                yield {
                    'type': 'progress',
                    'current': idx + 1,
                    'total': n_slots,
                    'message': (
                        f'Проход {pass_num + 1}: {label} '
                        f'— {assignment.school_class.name}'
                    ),
                }
                if kind == 'pair' and assignment.remaining_hours >= 2:
                    n = self._place_pair_first_fit(
                        assignment, school_level, working_days, max_lessons
                    )
                else:
                    n = self._place_one_teacher_hour_first_fit(
                        assignment, school_level, working_days, max_lessons
                    )
                if n:
                    scheduled_count += n
                    round_placed += n

            if round_placed == 0:
                break

        leftover = [a for a in assignments if a.remaining_hours > 0]
        if leftover:
            n_left = max(1, sum(a.remaining_hours for a in leftover))
            step = 0
            for kind, assignment in self._schedule_units(leftover, pair_mode):
                step += 1
                yield {
                    'type': 'progress',
                    'current': step,
                    'total': n_left,
                    'message': (
                        f'Перебор вариантов: {assignment.subject.name} '
                        f'— {assignment.school_class.name}'
                    ),
                }
                n = 0
                if kind == 'pair' and assignment.remaining_hours >= 2:
                    n = self._place_pair_first_fit(
                        assignment, school_level, working_days, max_lessons
                    )
                if not n:
                    n = self._try_place_hour_by_relocating(
                        assignment, school_level, working_days, max_lessons
                    )
                    if kind == 'pair' and assignment.remaining_hours > 0:
                        extra = self._try_place_hour_by_relocating(
                            assignment, school_level, working_days, max_lessons
                        )
                        n += extra
                if n:
                    scheduled_count += n

        leftover = [a for a in assignments if a.remaining_hours > 0]
        if leftover:
            yield {
                'type': 'progress',
                'current': 1,
                'total': 1,
                'message': 'Перебор вариантов: перекладка смены учителя',
            }
            n = self._repack_teacher_shifts(
                teacher_id, assignments, school_level, working_days, max_lessons,
                pair_mode=pair_mode,
            )
            scheduled_count += n

        self.session.commit()

        solver_result = self.graph_solver.solve_residuals(
            school_level=school_level,
            teacher_id=teacher_id,
            max_diag_items=20,
        )
        scheduled_count += solver_result.placed_count
        yield {
            'type': 'done',
            'count': scheduled_count,
            'solver_used': True,
            'solver_placed_count': solver_result.placed_count,
            'unplaced': solver_result.unplaced,
            'diagnostics': solver_result.diagnostics,
        }

    def schedule_class_day(self, class_id, day, school_level='elementary'):
        """
        Fill one day for a class with available lessons.
        Distributes lessons evenly.
        
        Returns count of scheduled lessons.
        """
        school_class = self.session.get(SchoolClass, class_id)
        shift = school_class.shift if school_class and school_class.shift_id else None
        max_lessons = shift.max_lessons_per_day if shift else 7

        # Get unscheduled assignments for this class
        aq = self.session.query(TeachingAssignment).filter(
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.teacher_id.isnot(None)
        )
        if self.school_id is not None:
            aq = aq.filter(TeachingAssignment.school_id == self.school_id)
        assignments = aq.all()

        # Get assignments with remaining hours, sorted by remaining hours (most first)
        available = []
        for a in assignments:
            remaining = a.remaining_hours
            if remaining > 0:
                available.append((a, remaining))
        available.sort(key=lambda x: -x[1])

        scheduled_count = 0
        # Несколько проходов по урокам 1..N: после первого прохода часть слотов
        # может остаться пустой (порядок перебора available), следующий проход с
        # пересортировкой по остатку часов заполняет их.
        max_day_passes = max(max_lessons, 12)

        for _pass in range(max_day_passes):
            if not available:
                break
            available.sort(key=lambda x: -x[1])
            round_placed = 0

            for lesson_num in range(1, max_lessons + 1):
                if not available:
                    break

                pair_count = self._try_place_subgroup_pair(
                    available, class_id, day, lesson_num, school_level
                )
                if pair_count:
                    scheduled_count += pair_count
                    round_placed += pair_count
                    continue

                ordered_available = self._prioritize_available_for_adjacent(
                    available, class_id, day, lesson_num
                )
                for assignment, remaining in ordered_available:
                    i = next((idx for idx, (a, _r) in enumerate(available) if a.id == assignment.id), None)
                    if i is None:
                        continue
                    classroom_id = self._get_classroom_for_cell(assignment, school_level)
                    errors = self.validator.validate_cell(
                        assignment=assignment,
                        day=day,
                        lesson=lesson_num,
                        classroom_id=classroom_id
                    )

                    if not errors:
                        cell = ScheduleCell(
                            **({'school_id': self.school_id} if self.school_id is not None else {}),
                            class_id=class_id,
                            day_of_week=day,
                            lesson_number=lesson_num,
                            assignment_id=assignment.id,
                            classroom_id=classroom_id
                        )
                        self.session.add(cell)
                        self.session.flush()

                        new_remaining = remaining - 1
                        if new_remaining <= 0:
                            available.pop(i)
                        else:
                            available[i] = (assignment, new_remaining)

                        comp = 0
                        if assignment.group_number is not None:
                            comp = self._place_complementary_in_slot(
                                available, assignment, class_id, day, lesson_num, school_level
                            )
                            if (
                                comp == 0
                                and self._other_subgroup_needs_parallel_pair(assignment, available)
                            ):
                                self.session.delete(cell)
                                self.session.flush()
                                self._restore_available_hours(
                                    available, assignment, remaining
                                )
                                continue

                        scheduled_count += 1 + comp
                        round_placed += 1 + comp

                        break

            if round_placed == 0:
                break

        self.session.commit()
        return scheduled_count

    def _restore_available_hours(self, available, assignment, original_remaining):
        """Вернуть час после отката ячейки (не удалось поставить вторую подгруппу)."""
        for idx, (a, rem) in enumerate(available):
            if a.id == assignment.id:
                available[idx] = (assignment, original_remaining)
                return
        available.append((assignment, original_remaining))

    def _decrement_available_assignment(self, available, assignment):
        """Списать один час у назначения в списке available."""
        for idx, (a, rem) in enumerate(available):
            if a.id != assignment.id:
                continue
            new_rem = rem - 1
            if new_rem <= 0:
                available.pop(idx)
            else:
                available[idx] = (assignment, new_rem)
            return

    def _other_subgroup_needs_parallel_pair(self, assignment, available):
        """
        Есть ли вторая подгруппа по тому же предмету с оставшимися часами и другим учителем.
        Тогда одна подгруппа в слоте без второй — недопустима (нужен откат или пара).
        """
        if assignment.group_number is None:
            return False
        for a, rem in available:
            if rem <= 0 or a.id == assignment.id:
                continue
            if a.subject_id != assignment.subject_id or a.group_number is None:
                continue
            if a.group_number == assignment.group_number:
                continue
            if a.teacher_id == assignment.teacher_id:
                return False
            return True
        return False

    def _try_place_subgroup_pair(self, available, class_id, day, lesson_num, school_level):
        """
        Поставить в слот обе подгруппы одного предмета (разные учителя) или ни одной.
        Возвращает 0 или 2.
        """
        from collections import defaultdict

        by_subject = defaultdict(list)
        for idx, (a, rem) in enumerate(available):
            if rem <= 0 or a.group_number is None:
                continue
            by_subject[a.subject_id].append((idx, a, rem))

        for _subject_id, rows in by_subject.items():
            if len(rows) < 2:
                continue
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    _idx_i, a_i, rem_i = rows[i]
                    _idx_j, a_j, rem_j = rows[j]
                    if a_i.group_number == a_j.group_number:
                        continue
                    if a_i.teacher_id and a_i.teacher_id == a_j.teacher_id:
                        continue
                    c_i = self._get_classroom_for_cell(a_i, school_level)
                    c_j = self._get_classroom_for_cell(a_j, school_level)
                    e_i = self.validator.validate_cell(
                        a_i, day, lesson_num, classroom_id=c_i
                    )
                    if e_i:
                        continue
                    cell_i = ScheduleCell(
                        **({'school_id': self.school_id} if self.school_id is not None else {}),
                        class_id=class_id,
                        day_of_week=day,
                        lesson_number=lesson_num,
                        assignment_id=a_i.id,
                        classroom_id=c_i,
                    )
                    self.session.add(cell_i)
                    self.session.flush()
                    e_j = self.validator.validate_cell(
                        a_j, day, lesson_num, classroom_id=c_j
                    )
                    if e_j:
                        self.session.delete(cell_i)
                        self.session.flush()
                        continue
                    cell_j = ScheduleCell(
                        **({'school_id': self.school_id} if self.school_id is not None else {}),
                        class_id=class_id,
                        day_of_week=day,
                        lesson_number=lesson_num,
                        assignment_id=a_j.id,
                        classroom_id=c_j,
                    )
                    self.session.add(cell_j)
                    self._decrement_available_assignment(available, a_i)
                    self._decrement_available_assignment(available, a_j)
                    return 2
        return 0

    def _place_complementary_in_slot(self, available, placed_assignment, class_id, day, lesson_num, school_level='elementary'):
        """
        After placing a subgroup from the available list,
        find and place the complementary subgroup (same subject, other group) in the same slot.
        Returns 1 if placed, 0 otherwise.
        """
        if placed_assignment.group_number is None:
            return 0
        placed_group_number = placed_assignment.group_number
        subject_id = placed_assignment.subject_id

        for i, (assignment, remaining) in enumerate(available):
            if assignment.group_number is None:
                continue
            if assignment.subject_id != subject_id:
                continue
            if assignment.group_number == placed_group_number:
                continue

            classroom_id = self._get_classroom_for_cell(assignment, school_level)
            errors = self.validator.validate_cell(
                assignment=assignment,
                day=day,
                lesson=lesson_num,
                classroom_id=classroom_id
            )
            if not errors:
                cell = ScheduleCell(
                    **({'school_id': self.school_id} if self.school_id is not None else {}),
                    class_id=class_id,
                    day_of_week=day,
                    lesson_number=lesson_num,
                    assignment_id=assignment.id,
                    classroom_id=classroom_id
                )
                self.session.add(cell)

                new_remaining = remaining - 1
                if new_remaining <= 0:
                    available.pop(i)
                else:
                    available[i] = (assignment, new_remaining)
                return 1
        return 0

    def _try_place_complementary_subgroup(self, placed_assignment, day, lesson, school_level='elementary'):
        """
        After placing a subgroup in teacher-ladder mode,
        find and place the complementary subgroup (possibly from another teacher)
        in the same slot. Returns 1 if placed, 0 otherwise.
        """
        cq = self.session.query(TeachingAssignment).filter(
            TeachingAssignment.class_id == placed_assignment.class_id,
            TeachingAssignment.subject_id == placed_assignment.subject_id,
            TeachingAssignment.group_number.isnot(None),
            TeachingAssignment.group_number != placed_assignment.group_number,
            TeachingAssignment.teacher_id.isnot(None)
        )
        if self.school_id is not None:
            cq = cq.filter(TeachingAssignment.school_id == self.school_id)
        complementary_assignments = cq.all()

        for comp in complementary_assignments:
            if comp.remaining_hours <= 0:
                continue
            classroom_id = self._get_classroom_for_cell(comp, school_level)
            errors = self.validator.validate_cell(
                assignment=comp,
                day=day,
                lesson=lesson,
                classroom_id=classroom_id
            )
            if not errors:
                cell = ScheduleCell(
                    **({'school_id': self.school_id} if self.school_id is not None else {}),
                    class_id=comp.class_id,
                    day_of_week=day,
                    lesson_number=lesson,
                    assignment_id=comp.id,
                    classroom_id=classroom_id
                )
                self.session.add(cell)
                return 1
        return 0

    def auto_schedule_all(self, school_level='elementary', solver='legacy', shift_id=None,
                          time_limit_sec=60.0, random_seed=1):
        """
        Automatically schedule all unscheduled lessons.
        Uses a combination of strategies.
        
        Returns total count of scheduled lessons.
        """
        result = self.auto_schedule_all_result(
            school_level, solver=solver, shift_id=shift_id,
            time_limit_sec=time_limit_sec, random_seed=random_seed,
        )
        if result.get('type') == 'error':
            return 0
        return result.get('count', 0)

    def auto_schedule_all_result(self, school_level='elementary', solver='legacy', shift_id=None,
                                 time_limit_sec=60.0, random_seed=1):
        """Return last done- или error-event для не-stream маршрутов."""
        last = {'type': 'done', 'count': 0}
        for event in self.auto_schedule_all_iter(
            school_level, solver=solver, shift_id=shift_id,
            time_limit_sec=time_limit_sec, random_seed=random_seed,
        ):
            if event.get('type') in ('done', 'error'):
                last = event
        return last

    def auto_schedule_all_iter(self, school_level='elementary', solver='legacy', shift_id=None,
                               time_limit_sec=60.0, random_seed=1):
        """
        Автозаполнение с событиями прогресса (класс × день).
        solver: 'legacy' (эвристики + граф) или 'cp_sat_mvp' (для одной смены, shift_id обязателен).
        """
        if solver == 'cp_sat_mvp':
            if shift_id is None:
                yield {
                    'type': 'error',
                    'message': 'Для стратегии CP-SAT укажите shift_id (смену)',
                }
                return
            yield from self.cp_sat_schedule_shift_iter(
                shift_id=int(shift_id),
                school_level=school_level,
                time_limit_sec=float(time_limit_sec),
                random_seed=int(random_seed),
            )
            return

        classes = self._scope(self.session.query(SchoolClass), SchoolClass).filter_by(school_level=school_level)\
            .order_by(SchoolClass.grade, SchoolClass.name).all()
        tq = self.session.query(Teacher).join(TeachingAssignment).join(SchoolClass).filter(
            SchoolClass.school_level == school_level
        )
        if self.school_id is not None:
            tq = tq.filter(Teacher.school_id == self.school_id, SchoolClass.school_id == self.school_id)
        teachers = tq.distinct().order_by(Teacher.full_name).all()

        # Если сетка уровня пустая, сначала используем teacher-ladder:
        # это заметно уменьшает окна у учителей на старте.
        hq = self.session.query(ScheduleCell).join(SchoolClass).filter(
            SchoolClass.school_level == school_level
        )
        if self.school_id is not None:
            hq = hq.filter(ScheduleCell.school_id == self.school_id)
        has_cells = hq.first() is not None

        total_steps = 0
        for sc in classes:
            sh = sc.shift if sc.shift_id else None
            wd = sh.working_days if sh else 5
            total_steps += wd

        total_scheduled = 0
        max_rounds = 12
        for round_num in range(1, max_rounds + 1):
            round_scheduled = 0

            if not has_cells:
                # Раунд teacher-ladder на пустой сетке
                t_total = len(teachers) if teachers else 1
                for t_idx, teacher in enumerate(teachers, start=1):
                    yield {
                        'type': 'progress',
                        'current': t_idx,
                        'total': t_total,
                        'message': f'Раунд {round_num}: учитель {teacher.full_name}',
                    }
                    c = self.schedule_by_teacher_ladder(teacher.id, school_level)
                    round_scheduled += c
                    total_scheduled += c
                has_cells = True
            else:
                # Раунд class-day (добивка/выравнивание)
                step = 0
                for school_class in classes:
                    shift = school_class.shift if school_class.shift_id else None
                    wd = shift.working_days if shift else 5
                    for day in range(1, wd + 1):
                        step += 1
                        yield {
                            'type': 'progress',
                            'current': step,
                            'total': total_steps if total_steps else 1,
                            'message': f'Раунд {round_num}: {school_class.name}, день {day}',
                        }
                        count = self.schedule_class_day(school_class.id, day, school_level)
                        round_scheduled += count
                        total_scheduled += count

                # После class-day — дополнительная добивка по учителям
                # (часто закрывает остатки из-за порядка обхода классов).
                for teacher in teachers:
                    c = self.schedule_by_teacher_ladder(teacher.id, school_level)
                    round_scheduled += c
                    total_scheduled += c

            if round_scheduled == 0:
                break

        solver_result = self.graph_solver.solve_residuals(
            school_level=school_level,
            max_diag_items=20,
        )
        total_scheduled += solver_result.placed_count
        yield {
            'type': 'done',
            'count': total_scheduled,
            'solver_used': True,
            'solver_placed_count': solver_result.placed_count,
            'unplaced': solver_result.unplaced,
            'diagnostics': solver_result.diagnostics,
        }

    def clear_schedule(self, school_level=None, class_id=None, teacher_id=None):
        """
        Clear schedule (delete cells) with optional filters.
        """
        query = self.session.query(ScheduleCell)
        if self.school_id is not None:
            query = query.filter(ScheduleCell.school_id == self.school_id)

        if class_id:
            query = query.filter(ScheduleCell.class_id == class_id)
        elif school_level:
            query = query.join(SchoolClass).filter(SchoolClass.school_level == school_level)

        if teacher_id:
            query = query.join(TeachingAssignment).filter(TeachingAssignment.teacher_id == teacher_id)

        cells = query.all()
        count = len(cells)
        for cell in cells:
            self.session.delete(cell)
        self.session.commit()
        return count

    def build_unscheduled_diagnostics(
        self, school_level='elementary', teacher_id=None, class_id=None, max_items=20
    ):
        """
        Диагностика нераспределённых часов:
        для каждого назначения с remaining_hours > 0 показывает топ причин,
        почему слоты не проходят validate_cell.
        """
        query = self.session.query(TeachingAssignment).join(SchoolClass).filter(
            SchoolClass.school_level == school_level,
            TeachingAssignment.teacher_id.isnot(None),
        )
        if self.school_id is not None:
            query = query.filter(
                TeachingAssignment.school_id == self.school_id,
                SchoolClass.school_id == self.school_id,
            )
        if teacher_id:
            query = query.filter(TeachingAssignment.teacher_id == teacher_id)
        if class_id:
            query = query.filter(TeachingAssignment.class_id == class_id)

        diagnostics = []
        for a in query.all():
            remaining = a.remaining_hours
            if remaining <= 0:
                continue

            shift = a.school_class.shift if a.school_class and a.school_class.shift_id else None
            working_days = shift.working_days if shift else 5
            max_lessons = shift.max_lessons_per_day if shift else 7
            lesson_start = shift.start_lesson if shift else 1
            lesson_end_excl = (
                shift.start_lesson + shift.lessons_count if shift else max_lessons + 1
            )

            reasons = Counter()
            feasible_slots = 0
            checked_slots = 0
            classroom_id = self._get_classroom_for_cell(a, school_level)

            for day in range(1, working_days + 1):
                for lesson in range(lesson_start, lesson_end_excl):
                    checked_slots += 1
                    errors = self.validator.validate_cell(
                        assignment=a,
                        day=day,
                        lesson=lesson,
                        classroom_id=classroom_id,
                    )
                    if not errors:
                        feasible_slots += 1
                        continue
                    for err in errors:
                        reasons[err] += 1

            top_reasons = [
                {'reason': reason, 'count': count}
                for reason, count in reasons.most_common(3)
            ]
            diagnostics.append({
                'assignment_id': a.id,
                'class_name': a.school_class.name if a.school_class else '?',
                'subject_name': a.subject.display_name if a.subject else '?',
                'teacher_name': a.teacher.display_name if a.teacher else '?',
                'remaining_hours': remaining,
                'feasible_slots': feasible_slots,
                'checked_slots': checked_slots,
                'top_reasons': top_reasons,
            })

        diagnostics.sort(
            key=lambda x: (-x['remaining_hours'], x['feasible_slots'], x['class_name'], x['subject_name'])
        )
        return diagnostics[:max_items]

    def get_classroom_warnings(self, school_level=None):
        """
        Собирает предупреждения об уроках без привязки к кабинету.
        Returns: [(type, message, cell_or_entity), ...]
        """
        warnings = []
        seen = set()  # (type, id) для дедупликации

        if school_level:
            settings = self._settings_for(school_level)
            mode = settings.classroom_mode if settings else 'class_room'
        else:
            settings = None
            mode = 'class_room'

        # Уроки без кабинета в расписании
        cells = self.session.query(ScheduleCell).filter(ScheduleCell.classroom_id.is_(None))
        if self.school_id is not None:
            cells = cells.filter(ScheduleCell.school_id == self.school_id)
        if school_level:
            cells = cells.join(SchoolClass).filter(SchoolClass.school_level == school_level)
        for cell in cells.all():
            a = cell.assignment
            s = a.subject
            if s.requires_fixed_classroom and not (a.preferred_classroom_id or s.default_classroom_id):
                key = ('fixed_no_room', cell.class_id, s.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('fixed_no_room', f'{cell.school_class.name} {s.name}: предмет требует кабинет', cell))
            elif mode == 'teacher_room' and a.teacher and not a.teacher.home_classroom_id:
                key = ('teacher_no_room', a.teacher_id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('teacher_no_room', f'{a.teacher.display_name} не имеет прикреплённого кабинета', cell))
            elif mode == 'class_room' and not cell.school_class.home_classroom_id:
                key = ('class_no_room', cell.class_id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('class_no_room', f'{cell.school_class.name} не имеет прикреплённого кабинета', cell))

        # Учителя без кабинета (для teacher_room) — если ещё нет уроков в расписании
        if school_level and mode == 'teacher_room':
            tq = self.session.query(Teacher).join(TeachingAssignment).join(SchoolClass).filter(
                SchoolClass.school_level == school_level,
                Teacher.home_classroom_id.is_(None)
            )
            if self.school_id is not None:
                tq = tq.filter(Teacher.school_id == self.school_id)
            for t in tq.distinct().all():
                key = ('teacher_no_room', t.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('teacher_no_room', f'Учитель {t.display_name} не имеет прикреплённого кабинета', t))

        # Классы без кабинета (для class_room)
        if school_level and mode == 'class_room':
            for c in self._scope(self.session.query(SchoolClass), SchoolClass).filter_by(school_level=school_level).filter(
                    SchoolClass.home_classroom_id.is_(None)).all():
                if c.assignments.filter(TeachingAssignment.teacher_id.isnot(None)).first():
                    key = ('class_no_room', c.id)
                    if key not in seen:
                        seen.add(key)
                        warnings.append(('class_no_room', f'Класс {c.name} не имеет прикреплённого кабинета', c))

        # Предметы с requires_fixed_classroom без default_classroom
        for s in self._scope(self.session.query(Subject), Subject).filter_by(requires_fixed_classroom=True).filter(
                Subject.default_classroom_id.is_(None)).all():
            if any(not a.preferred_classroom_id for a in s.assignments):
                key = ('fixed_subject_default', s.id)
                if key not in seen:
                    seen.add(key)
                    warnings.append(('fixed_subject_default',
                        f'Предмет "{s.name}" требует кабинет, но не указан кабинет по умолчанию', s))

        return warnings
