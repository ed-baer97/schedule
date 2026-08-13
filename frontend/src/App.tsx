import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layouts/AppLayout'
import { ScheduleLayout } from './layouts/ScheduleLayout'
import { AssignmentsPage } from './pages/AssignmentsPage'
import { AutoSchedulerPage } from './pages/AutoSchedulerPage'
import { ClassroomsPage } from './pages/ClassroomsPage'
import { DashboardPage } from './pages/DashboardPage'
import { ImportPage } from './pages/ImportPage'
import { ReportsClassPage } from './pages/ReportsClassPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReportsTeacherPage } from './pages/ReportsTeacherPage'
import { SchedulePage } from './pages/SchedulePage'
import { SchoolClassesPage } from './pages/SchoolClassesPage'
import { ShiftsPage } from './pages/ShiftsPage'
import { SubjectAssignmentsPage } from './pages/SubjectAssignmentsPage'
import { SubjectsPage } from './pages/SubjectsPage'
import { TeachersPage } from './pages/TeachersPage'
import { WorkloadPage } from './pages/WorkloadPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="teachers" element={<TeachersPage />} />
        <Route path="classrooms" element={<ClassroomsPage />} />
        <Route path="school-classes" element={<SchoolClassesPage />} />
        <Route path="shifts" element={<ShiftsPage />} />
        <Route path="subjects" element={<SubjectsPage />} />
        <Route path="subjects/:id/assignments" element={<SubjectAssignmentsPage />} />
        <Route path="workload" element={<WorkloadPage />} />
        <Route path="schedule" element={<ScheduleLayout />}>
          <Route index element={<SchedulePage />} />
          <Route path="auto" element={<AutoSchedulerPage />} />
          <Route path="settings" element={<Navigate to="/schedule/auto" replace />} />
        </Route>
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/class/:id" element={<ReportsClassPage />} />
        <Route path="reports/teacher/:id" element={<ReportsTeacherPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
