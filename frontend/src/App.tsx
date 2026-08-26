import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './layouts/AppLayout'
import { ScheduleLayout } from './layouts/ScheduleLayout'
import { AdminSchoolsPage } from './pages/AdminSchoolsPage'
import { AutoSchedulerPage } from './pages/AutoSchedulerPage'
import { ClassroomsPage } from './pages/ClassroomsPage'
import { DashboardPage } from './pages/DashboardPage'
import { ImportPage } from './pages/ImportPage'
import { LoginPage } from './pages/LoginPage'
import { ReportsClassPage } from './pages/ReportsClassPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReportsTeacherPage } from './pages/ReportsTeacherPage'
import { SchedulePage } from './pages/SchedulePage'
import { SchoolClassesPage } from './pages/SchoolClassesPage'
import { ShiftsPage } from './pages/ShiftsPage'
import { SubjectAssignmentsPage } from './pages/SubjectAssignmentsPage'
import { SubjectsPage } from './pages/SubjectsPage'
import { TeacherLoadPage } from './pages/TeacherLoadPage'
import { TeachersPage } from './pages/TeachersPage'
import { WorkloadPage } from './pages/WorkloadPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="container py-5 text-center text-muted">Загрузка сессии…</div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'platform_admin' && !user.school_id) {
    return <Navigate to="/admin" replace />
  }
  return <>{children}</>
}

function RequirePlatformAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="container py-5 text-center text-muted">Загрузка сессии…</div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'platform_admin') return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/admin"
        element={
          <RequirePlatformAdmin>
            <AdminSchoolsPage />
          </RequirePlatformAdmin>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="teachers" element={<TeachersPage />} />
        <Route path="teacher-load" element={<TeacherLoadPage />} />
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
        <Route path="assignments" element={<Navigate to="/subjects" replace />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/class/:id" element={<ReportsClassPage />} />
        <Route path="reports/teacher/:id" element={<ReportsTeacherPage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
