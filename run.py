"""
Entry point for the School Schedule application
"""
from app import create_app, db
from app.models import Teacher, Classroom, SchoolClass, Shift, Subject, TeachingAssignment, ScheduleCell, ScheduleSettings

app = create_app()


@app.shell_context_processor
def make_shell_context():
    """Make database models available in flask shell"""
    return {
        'db': db,
        'Teacher': Teacher,
        'Classroom': Classroom,
        'SchoolClass': SchoolClass,
        'Shift': Shift,
        'Subject': Subject,
        'TeachingAssignment': TeachingAssignment,
        'ScheduleCell': ScheduleCell,
        'ScheduleSettings': ScheduleSettings,
    }


if __name__ == '__main__':
    app.run(debug=True, port=5000)
