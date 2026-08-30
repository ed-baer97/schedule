"""
Automatic schedule generation service
"""
from app.domain.preferences import WEIGHT_MAX, clamp_weight
from app.domain.schedule_rules import groups_can_share_slot
from app.domain.school_class import (
    SPLIT_GRADE_BANDS,
    SPLIT_WHOLE_SHIFT,
    partition_classes_by_grade_bands,
)
from app.models import SchoolClass, TeachingAssignment, ScheduleCell
from app.services.assignment_hours import remaining_for
from app.services.classroom_resolver import (
    load_classroom_facts,
    load_settings,
    pick_classroom,
    pick_classroom_for,
)
from app.services.schedule_service import ScheduleService
from app.services.schedule_solver import CpSatScheduleSolver, ResidualGraphSolver
from app.services.validators import ScheduleValidator


class AutoScheduler:
    """
    Service for automatic schedule generation.
    Implements different strategies for scheduling.
    Supports: teacher_room (дети приходят к учителю), class_room (учитель приходит к классу).
    """

    def __init__(self, session, school_id: int, should_stop=None, on_progress=None):
        self.session = session
        self.school_id = school_id
        self._should_stop = should_stop
        self._on_progress = on_progress
        self.validator = ScheduleValidator(self.session, school_id=school_id)
        self._schedule = ScheduleService(session, school_id)
        self.graph_solver = ResidualGraphSolver(
            self._get_classroom_for_cell, session=self.session, school_id=school_id
        )
        self.cp_sat_solver = CpSatScheduleSolver(
            self._get_classroom_for_cell, session=self.session, school_id=school_id
        )
        self._ladder_day_cache: dict[tuple[int, int], dict] = {}

    def _report(self, current: int, total: int, message: str) -> None:
        if self._on_progress is None:
            return
        try:
            self._on_progress(current, total, message)
        except Exception:
            pass

    def _stopped(self) -> bool:
        if self._should_stop is None:
            return False
        try:
            return bool(self._should_stop())
        except Exception:
            return False

    def _cancelled_event(self, count=0, message='Остановлено'):
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
        return {'type': 'cancelled', 'count': count, 'message': message}

    def _settings_for(self, school_level):
        return load_settings(self.session, self.school_id, school_level)

    def cp_sat_schedule_shift_iter(
        self,
        shift_id: int,
        school_level: str = "elementary",
        time_limit_sec: float = 60.0,
        random_seed: int = 1,
        class_ids: list[int] | None = None,
        progress_prefix: str | None = None,
        hours_first: str = "more",
    ):
        """
        CP-SAT: полная пересборка расписания для одной смены (переназначение слотов).
        ``class_ids`` ограничивает кусок смены (параллели классов).
        """

        def _emit(cur: int, tot: int, msg: str) -> None:
            text = f"{progress_prefix}: {msg}" if progress_prefix else msg
            self._report(cur, tot, text)

        load_msg = "Загрузка классов и нагрузки…"
        yield {
            "type": "progress",
            "current": 2,
            "total": 100,
            "message": f"{progress_prefix}: {load_msg}" if progress_prefix else load_msg,
        }
        if self._stopped():
            yield self._cancelled_event()
            return
        result = self.cp_sat_solver.solve_shift(
            shift_id=shift_id,
            school_level=school_level,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            should_stop=self._should_stop,
            on_progress=_emit,
            class_ids=class_ids,
            hours_first=hours_first,
        )
        if result.status == "CANCELLED" or self._stopped():
            yield self._cancelled_event()
            return
        if result.status in ("ERROR", "MODEL_INVALID", "INFEASIBLE"):
            reasons = [
                d.get("reason") for d in (result.diagnostics or []) if d.get("reason")
            ]
            message = result.error_message or (
                reasons[0] if reasons else "Ошибка CP-SAT"
            )
            if progress_prefix:
                message = f"{progress_prefix}: {message}"
            yield {
                "type": "error",
                "message": message,
                "diagnostics": result.diagnostics,
                "cp_sat_status": result.status,
                "solver_status": result.solver_status,
                "wall_time_sec": result.wall_time_sec,
                "count": 0,
            }
            return
        write_msg = "Запись расписания в сетку…"
        yield {
            "type": "progress",
            "current": 99,
            "total": 100,
            "message": f"{progress_prefix}: {write_msg}" if progress_prefix else write_msg,
        }
        done = {
            "type": "done",
            "count": result.placed_count,
            "cp_sat_status": result.status,
            "solver_status": result.solver_status,
            "objective": result.objective,
            "wall_time_sec": result.wall_time_sec,
            "diagnostics": result.diagnostics,
        }
        if result.status in ("INFEASIBLE", "UNKNOWN"):
            done["solver_used"] = False
        else:
            done["solver_used"] = True
        yield done

    def repair_iter(
        self,
        school_level: str = "elementary",
        teacher_id: int | None = None,
        class_id: int | None = None,
    ):
        """Дозаполнить непроставленные часы через residual solver (тот же write-path)."""
        yield {
            "type": "progress",
            "current": 0,
            "total": 1,
            "message": "Repair: дозаполнение оставшихся часов…",
        }
        if self._stopped():
            yield self._cancelled_event()
            return
        result = self.graph_solver.solve_residuals(
            school_level=school_level,
            teacher_id=teacher_id,
            class_id=class_id,
            max_diag_items=20,
            should_stop=self._should_stop,
        )
        if self._stopped():
            yield self._cancelled_event(result.placed_count)
            return
        yield {
            "type": "done",
            "count": result.placed_count,
            "unplaced": result.unplaced,
            "diagnostics": result.diagnostics,
            "solver_used": True,
            "message": f"Repair: добавлено уроков: {result.placed_count}",
        }

    def _get_teacher_lessons_for_class_day(self, class_id, day):
        """Map teacher_id -> set(lesson_number) for class/day."""
        key = (int(class_id), int(day))
        cached = self._ladder_day_cache.get(key)
        if cached is not None:
            return cached
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
        self._ladder_day_cache[key] = lessons_by_teacher
        return lessons_by_teacher

    def _touch_ladder_day(self, class_id, day):
        self._ladder_day_cache.pop((int(class_id), int(day)), None)

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
            return [x for x in base if x not in existing]

        anchor = next(iter(existing))
        around = []
        if anchor + 1 <= max_lessons:
            around.append(anchor + 1)
        if anchor - 1 >= 1:
            around.append(anchor - 1)
        return [x for x in around if x not in existing]

    def _get_classroom_for_cell(
        self, assignment, school_level, day=None, lesson=None, exclude_cell_id=None
    ):
        """
        Pick classroom for a cell. With day/lesson uses free capacity in the pool;
        otherwise returns the best-ranked candidate.
        """
        if day is not None and lesson is not None:
            return pick_classroom_for(
                self.session,
                self.school_id,
                assignment,
                school_level,
                day=day,
                lesson=lesson,
                exclude_cell_id=exclude_cell_id,
            )
        settings = self._settings_for(school_level)
        rooms = load_classroom_facts(self.session, self.school_id)
        return pick_classroom(assignment, settings, rooms)

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

    def _strict_consecutive_pairs(self, school_level):
        """Slider 10: do not split leftover doubles into singleton hours."""
        if not self._prefer_consecutive_pairs(school_level):
            return False
        settings = self._settings_for(school_level)
        raw = getattr(settings, "pref_adjacent_pairs", 5) if settings else 5
        return clamp_weight(raw) >= WEIGHT_MAX

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
            remaining = remaining_for(a)
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
            remaining = remaining_for(a)
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
        classroom_id = self._get_classroom_for_cell(
            assignment, school_level, day=day, lesson=lesson
        )
        errors = self.validator.validate_cell(
            assignment=assignment,
            day=day,
            lesson=lesson,
            classroom_id=classroom_id,
        )
        if errors:
            return 0
        self._schedule.insert_cell(
            class_id=assignment.class_id,
            day_of_week=day,
            lesson_number=lesson,
            assignment_id=assignment.id,
            classroom_id=classroom_id,
        )
        self._touch_ladder_day(assignment.class_id, day)
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
        moves = []
        for c in bundle:
            if c.day_of_week == new_day and c.lesson_number == new_lesson:
                return False
            room = self._get_classroom_for_cell(
                c.assignment,
                school_level,
                day=new_day,
                lesson=new_lesson,
                exclude_cell_id=c.id,
            )
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
            has_teacher = bool(c.assignment and c.assignment.teacher_id)
            moves.append((c, room if has_teacher else None, has_teacher))

        for c, room, set_room in moves:
            self._schedule.reposition_cell(
                c.id,
                day_of_week=new_day,
                lesson_number=new_lesson,
                classroom_id=room,
                set_classroom=set_room,
                validate=False,
                commit=False,
            )
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
                assignment.class_id,
                day,
                lesson,
                assignment.group_number,
                subject_id=assignment.subject_id,
                assignment=assignment,
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
        if not cells:
            return
        self._schedule.delete_cells(
            cell_ids=[c.id for c in cells],
            commit=False,
        )
        self._ladder_day_cache.clear()

    def schedule_by_teacher_ladder_iter(self, teacher_id, school_level='elementary'):
        """
        То же, что schedule_by_teacher_ladder, но отдаёт события прогресса для потоковой отдачи.
        Если в настройках «2 урока» — сначала ставит сдвоенные уроки подряд, часы
        разных классов чередуются. Если не умещается — сдвигает уже поставленный
        урок этого учителя (без полного DFS по смене).
        """
        self._ladder_day_cache.clear()
        aq = self.session.query(TeachingAssignment)\
            .join(SchoolClass)\
            .filter(
                TeachingAssignment.teacher_id == teacher_id,
                SchoolClass.school_level == school_level,
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

        initial_total = sum(remaining_for(a) for a in assignments)
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
                if self._stopped():
                    yield self._cancelled_event(scheduled_count)
                    return
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
                if kind == 'pair' and remaining_for(assignment) >= 2:
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

        leftover = [a for a in assignments if remaining_for(a) > 0]
        strict_pairs = self._strict_consecutive_pairs(school_level)
        if leftover:
            n_left = max(1, sum(remaining_for(a) for a in leftover))
            step = 0
            for kind, assignment in self._schedule_units(leftover, pair_mode):
                if self._stopped():
                    yield self._cancelled_event(scheduled_count)
                    return
                step += 1
                yield {
                    'type': 'progress',
                    'current': step,
                    'total': n_left,
                    'message': (
                        f'Перестановка: {assignment.subject.name} '
                        f'— {assignment.school_class.name}'
                    ),
                }
                n = 0
                if kind == 'pair' and remaining_for(assignment) >= 2:
                    n = self._place_pair_first_fit(
                        assignment, school_level, working_days, max_lessons
                    )
                if not n and not (strict_pairs and kind == 'pair'):
                    n = self._try_place_hour_by_relocating(
                        assignment, school_level, working_days, max_lessons
                    )
                    if kind == 'pair' and remaining_for(assignment) > 0:
                        extra = self._try_place_hour_by_relocating(
                            assignment, school_level, working_days, max_lessons
                        )
                        n += extra
                if n:
                    scheduled_count += n

        if self._stopped():
            yield self._cancelled_event(scheduled_count)
            return

        self.session.commit()

        if strict_pairs:
            unplaced = [
                {
                    "assignment_id": a.id,
                    "remaining": remaining_for(a),
                    "reason": "Сдвоенные уроки (ползунок 10): остаток не разбивается на одиночные",
                }
                for a in assignments
                if remaining_for(a) > 0
            ]
            yield {
                'type': 'done',
                'count': scheduled_count,
                'solver_used': False,
                'unplaced': unplaced,
                'diagnostics': unplaced,
            }
            return

        solver_result = self.graph_solver.solve_residuals(
            school_level=school_level,
            teacher_id=teacher_id,
            max_diag_items=20,
            should_stop=self._should_stop,
        )
        if self._stopped():
            yield self._cancelled_event(scheduled_count + solver_result.placed_count)
            return
        scheduled_count += solver_result.placed_count
        yield {
            'type': 'done',
            'count': scheduled_count,
            'solver_used': True,
            'solver_placed_count': solver_result.placed_count,
            'unplaced': solver_result.unplaced,
            'diagnostics': solver_result.diagnostics,
        }

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
            TeachingAssignment.teacher_id.isnot(None),
            TeachingAssignment.school_id == self.school_id,
            TeachingAssignment.id != placed_assignment.id,
        )
        complementary_assignments = [
            a
            for a in cq.all()
            if groups_can_share_slot(
                placed_assignment.group_number,
                a.group_number,
                placed_assignment.subject_id,
                a.subject_id,
            )
        ]

        for comp in complementary_assignments:
            if remaining_for(comp) <= 0:
                continue
            classroom_id = self._get_classroom_for_cell(
                comp, school_level, day=day, lesson=lesson
            )
            errors = self.validator.validate_cell(
                assignment=comp,
                day=day,
                lesson=lesson,
                classroom_id=classroom_id
            )
            if not errors:
                self._schedule.insert_cell(
                    class_id=comp.class_id,
                    day_of_week=day,
                    lesson_number=lesson,
                    assignment_id=comp.id,
                    classroom_id=classroom_id,
                )
                self._touch_ladder_day(comp.class_id, day)
                return 1
        return 0

    def auto_schedule_all_result(
        self,
        school_level='elementary',
        shift_id=None,
        time_limit_sec=60.0,
        random_seed=1,
        split=SPLIT_WHOLE_SHIFT,
        hours_first="more",
    ):
        """Return last done- или error-event для не-stream маршрутов."""
        last = {'type': 'done', 'count': 0}
        for event in self.auto_schedule_all_iter(
            school_level,
            shift_id=shift_id,
            time_limit_sec=time_limit_sec,
            random_seed=random_seed,
            split=split,
            hours_first=hours_first,
        ):
            if event.get('type') in ('done', 'error'):
                last = event
        return last

    def auto_schedule_all_iter(
        self,
        school_level='elementary',
        shift_id=None,
        time_limit_sec=60.0,
        random_seed=1,
        split=SPLIT_WHOLE_SHIFT,
        hours_first="more",
    ):
        """Автозаполнение CP-SAT для одной смены (целиком или кусками по параллелям)."""
        if shift_id is None:
            yield {
                'type': 'error',
                'message': 'Укажите shift_id (смену)',
            }
            return
        sid = int(shift_id)
        limit = float(time_limit_sec)
        seed = int(random_seed)
        if split != SPLIT_GRADE_BANDS:
            yield from self.cp_sat_schedule_shift_iter(
                shift_id=sid,
                school_level=school_level,
                time_limit_sec=limit,
                random_seed=seed,
                hours_first=hours_first,
            )
            return

        shift_classes = (
            self.session.query(SchoolClass)
            .filter_by(
                shift_id=sid,
                school_level=school_level,
                school_id=self.school_id,
            )
            .order_by(SchoolClass.grade, SchoolClass.name)
            .all()
        )
        chunks = partition_classes_by_grade_bands(shift_classes, school_level)
        if len(chunks) <= 1:
            yield from self.cp_sat_schedule_shift_iter(
                shift_id=sid,
                school_level=school_level,
                time_limit_sec=limit,
                random_seed=seed,
                hours_first=hours_first,
            )
            return

        n_chunks = len(chunks)
        total_placed = 0
        wall_sum = 0.0
        diagnostics: list = []
        last_status = None
        last_solver_status = None
        any_error = None
        used = False

        for i, (band, band_classes) in enumerate(chunks):
            if self._stopped():
                yield self._cancelled_event(total_placed)
                return
            prefix = f"Кусок {i + 1}/{n_chunks} ({band.label})"
            yield {
                "type": "progress",
                "current": int(100 * i / n_chunks),
                "total": 100,
                "message": f"{prefix}: старт, {len(band_classes)} кл.",
            }
            self._report(
                int(100 * i / n_chunks),
                100,
                f"{prefix}: старт, {len(band_classes)} кл.",
            )
            for event in self.cp_sat_schedule_shift_iter(
                shift_id=sid,
                school_level=school_level,
                time_limit_sec=limit,
                random_seed=seed,
                class_ids=[c.id for c in band_classes],
                progress_prefix=prefix,
                hours_first=hours_first,
            ):
                if event.get("type") == "cancelled":
                    yield self._cancelled_event(total_placed)
                    return
                if event.get("type") == "progress":
                    yield event
                    continue
                if event.get("type") == "error":
                    any_error = event
                    diagnostics.extend(event.get("diagnostics") or [])
                    last_status = event.get("cp_sat_status")
                    last_solver_status = event.get("solver_status")
                    wall_sum += float(event.get("wall_time_sec") or 0)
                    yield {
                        "type": "progress",
                        "current": int(100 * (i + 1) / n_chunks),
                        "total": 100,
                        "message": event.get("message") or f"{prefix}: ошибка",
                    }
                    break
                if event.get("type") == "done":
                    total_placed += int(event.get("count") or 0)
                    wall_sum += float(event.get("wall_time_sec") or 0)
                    last_status = event.get("cp_sat_status")
                    last_solver_status = event.get("solver_status")
                    used = used or bool(event.get("solver_used"))
                    diagnostics.extend(event.get("diagnostics") or [])
            try:
                self.session.expire_all()
            except Exception:
                pass

        if any_error is not None and total_placed == 0:
            yield {
                **any_error,
                "count": 0,
                "diagnostics": diagnostics or any_error.get("diagnostics"),
                "wall_time_sec": wall_sum,
            }
            return
        yield {
            "type": "done",
            "count": total_placed,
            "cp_sat_status": last_status,
            "solver_status": last_solver_status,
            "wall_time_sec": wall_sum,
            "diagnostics": diagnostics or None,
            "solver_used": used,
            "split": SPLIT_GRADE_BANDS,
            "chunks": n_chunks,
        }
