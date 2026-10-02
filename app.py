import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')

# База данных: локально SQLite, на Render — PostgreSQL из переменной окружения
database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ============ МОДЕЛИ ============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(20))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    teacher = db.relationship('User', foreign_keys=[teacher_id])


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    comment = db.Column(db.String(200))

    student = db.relationship('User', foreign_keys=[student_id])
    subject = db.relationship('Subject')


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    mark = db.Column(db.String(2), nullable=False)
    comment = db.Column(db.String(200))
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    student = db.relationship('User', foreign_keys=[student_id])
    teacher = db.relationship('User', foreign_keys=[teacher_id])


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(20), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    lesson_number = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    room = db.Column(db.String(20))
    time_start = db.Column(db.String(10))
    time_end = db.Column(db.String(10))

    subject = db.relationship('Subject')


class Homework(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    class_name = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    text = db.Column(db.Text, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    subject = db.relationship('Subject')
    teacher = db.relationship('User', foreign_keys=[teacher_id])


# ============ ДЕКОРАТОРЫ ============

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Доступ запрещён', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ============ КОНСТАНТЫ ============

DAY_NAMES = {
    1: 'Понедельник',
    2: 'Вторник',
    3: 'Среда',
    4: 'Четверг',
    5: 'Пятница'
}

MAX_LESSON = 9

QUARTERS = {
    1: {'name': 'I четверть', 'start': (9, 1), 'end': (10, 27)},
    2: {'name': 'II четверть', 'start': (11, 5), 'end': (12, 30)},
    3: {'name': 'III четверть', 'start': (1, 9), 'end': (3, 22)},
    4: {'name': 'IV четверть', 'start': (4, 1), 'end': (5, 31)},
}


def get_quarter_dates(quarter, year):
    q = QUARTERS[quarter]
    start = datetime(year, q['start'][0], q['start'][1]).date()
    end = datetime(year, q['end'][0], q['end'][1]).date()
    return start, end


def calculate_final_grade(average):
    if average is None:
        return None
    if average >= 4.5:
        return 5
    elif average >= 3.5:
        return 4
    elif average >= 2.5:
        return 3
    else:
        return 2


# ============ МАРШРУТЫ ============

@app.route('/')
def index():
    if 'user_id' in session:
        role = session['role']
        if role == 'student':
            return redirect(url_for('student_diary'))
        elif role == 'teacher':
            return redirect(url_for('teacher_journal'))
        elif role == 'admin':
            return redirect(url_for('admin_panel'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['full_name'] = user.full_name

            if user.role == 'student':
                return redirect(url_for('student_diary'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_journal'))
            elif user.role == 'admin':
                return redirect(url_for('admin_panel'))

        flash('Неверный логин или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------- УЧЕНИК ----------

@app.route('/diary')
@login_required
@role_required('student')
def student_diary():
    student = User.query.get(session['user_id'])
    grades = Grade.query.filter_by(student_id=student.id)\
        .order_by(Grade.date.desc()).all()

    subjects_data = {}
    for grade in grades:
        subj_name = grade.subject.name
        if subj_name not in subjects_data:
            subjects_data[subj_name] = []
        subjects_data[subj_name].append(grade)

    all_values = [g.value for g in grades]
    average = round(sum(all_values) / len(all_values), 2) if all_values else 0

    attendance_records = Attendance.query.filter_by(student_id=student.id)\
        .order_by(Attendance.date.desc()).all()

    attendance_stats = {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}
    for a in attendance_records:
        if a.mark in attendance_stats:
            attendance_stats[a.mark] += 1

    today = datetime.utcnow().date()
    week_later = today + timedelta(days=7)
    homework_list = Homework.query.filter(
        Homework.class_name == student.class_name,
        Homework.date >= today,
        Homework.date <= week_later
    ).order_by(Homework.date, Homework.subject_id).all()

    return render_template('student_diary.html',
                           student=student, subjects_data=subjects_data,
                           average=average, total_grades=len(grades),
                           attendance_records=attendance_records,
                           attendance_stats=attendance_stats,
                           homework_list=homework_list)


# ---------- УЧИТЕЛЬ ----------

@app.route('/journal')
@login_required
@role_required('teacher')
def teacher_journal():
    teacher = User.query.get(session['user_id'])
    students = User.query.filter_by(role='student')\
        .order_by(User.class_name, User.full_name).all()
    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    recent_grades = Grade.query.join(Subject)\
        .filter(Subject.teacher_id == teacher.id)\
        .order_by(Grade.date.desc()).limit(10).all()

    return render_template('teacher_journal.html',
                           teacher=teacher, students=students,
                           subjects=subjects, recent_grades=recent_grades)


@app.route('/grade/add', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def add_grade():
    teacher = User.query.get(session['user_id'])
    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    students = User.query.filter_by(role='student')\
        .order_by(User.class_name, User.full_name).all()

    if request.method == 'POST':
        grade = Grade(
            student_id=request.form.get('student_id'),
            subject_id=request.form.get('subject_id'),
            value=int(request.form.get('value')),
            comment=request.form.get('comment', ''),
            date=datetime.utcnow().date()
        )
        db.session.add(grade)
        db.session.commit()
        flash('Оценка успешно выставлена!', 'success')
        return redirect(url_for('teacher_journal'))

    return render_template('teacher_grade.html', subjects=subjects, students=students)


@app.route('/grade/delete/<int:grade_id>', methods=['POST'])
@login_required
@role_required('teacher')
def delete_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    db.session.delete(grade)
    db.session.commit()
    flash('Оценка удалена', 'success')
    return redirect(url_for('teacher_journal'))


# ---------- ПОСЕЩАЕМОСТЬ ----------

@app.route('/attendance')
@login_required
@role_required('teacher')
def attendance():
    teacher = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    selected_class = request.args.get('class_name', classes[0] if classes else None)
    selected_date_str = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = datetime.utcnow().date()

    students = []
    if selected_class:
        students = User.query.filter_by(role='student', class_name=selected_class)\
            .order_by(User.full_name).all()

    existing = {}
    if students:
        student_ids = [s.id for s in students]
        marks = Attendance.query.filter(
            Attendance.student_id.in_(student_ids),
            Attendance.date == selected_date
        ).all()
        for m in marks:
            existing[m.student_id] = m

    return render_template('attendance.html',
                           teacher=teacher, classes=classes,
                           students=students, selected_class=selected_class,
                           selected_date=selected_date,
                           selected_date_str=selected_date_str, existing=existing)


@app.route('/attendance/save', methods=['POST'])
@login_required
@role_required('teacher')
def save_attendance():
    teacher = User.query.get(session['user_id'])
    selected_date_str = request.form.get('date')
    selected_class = request.form.get('class_name')

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = datetime.utcnow().date()

    students = User.query.filter_by(role='student', class_name=selected_class).all()

    for student in students:
        mark = request.form.get(f'mark_{student.id}', '').strip().upper()
        comment = request.form.get(f'comment_{student.id}', '').strip()

        existing = Attendance.query.filter_by(
            student_id=student.id, date=selected_date
        ).first()

        if mark in ('Н', 'О', 'П', 'Б'):
            if existing:
                existing.mark = mark
                existing.comment = comment
                existing.teacher_id = teacher.id
            else:
                db.session.add(Attendance(
                    student_id=student.id, date=selected_date,
                    mark=mark, comment=comment, teacher_id=teacher.id
                ))
        else:
            if existing:
                db.session.delete(existing)

    db.session.commit()
    flash(f'Посещаемость за {selected_date.strftime("%d.%m.%Y")} сохранена!', 'success')
    return redirect(url_for('attendance', class_name=selected_class, date=selected_date_str))


# ---------- РАСПИСАНИЕ ----------

@app.route('/schedule')
@login_required
def schedule():
    role = session['role']
    user = User.query.get(session['user_id'])

    if role == 'student':
        view_class = user.class_name
        return render_template('schedule.html',
                               role=role, user=user, classes=[],
                               view_class=view_class,
                               schedule_data=get_schedule_for_class(view_class),
                               day_names=DAY_NAMES, max_lesson=MAX_LESSON)
    else:
        classes = sorted([c[0] for c in db.session.query(User.class_name)
                          .filter(User.role == 'student', User.class_name.isnot(None))
                          .distinct().all()])
        view_class = request.args.get('class_name', classes[0] if classes else None)

        return render_template('schedule.html',
                               role=role, user=user, classes=classes,
                               view_class=view_class,
                               schedule_data=get_schedule_for_class(view_class),
                               day_names=DAY_NAMES, max_lesson=MAX_LESSON)


def get_schedule_for_class(class_name):
    if not class_name:
        return {}
    items = Schedule.query.filter_by(class_name=class_name).all()
    return {(item.day_of_week, item.lesson_number): item for item in items}


@app.route('/schedule/edit', methods=['GET', 'POST'])
@login_required
@role_required('teacher', 'admin')
def schedule_edit():
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    if request.method == 'POST':
        class_name = request.form.get('class_name')
        action = request.form.get('action')

        if action == 'clear':
            Schedule.query.filter_by(class_name=class_name).delete()
            db.session.commit()
            flash(f'Расписание класса {class_name} очищено', 'success')
            return redirect(url_for('schedule_edit', class_name=class_name))

        Schedule.query.filter_by(class_name=class_name).delete()

        for day in range(1, 6):
            for lesson in range(1, MAX_LESSON + 1):
                subject_id = request.form.get(f'subject_{day}_{lesson}', '').strip()
                if subject_id:
                    db.session.add(Schedule(
                        class_name=class_name, day_of_week=day,
                        lesson_number=lesson, subject_id=int(subject_id),
                        room=request.form.get(f'room_{day}_{lesson}', '').strip(),
                        time_start=request.form.get(f'start_{day}_{lesson}', '').strip(),
                        time_end=request.form.get(f'end_{day}_{lesson}', '').strip()
                    ))

        db.session.commit()
        flash(f'Расписание для {class_name} сохранено!', 'success')
        return redirect(url_for('schedule', class_name=class_name))

    selected_class = request.args.get('class_name', classes[0] if classes else None)
    subjects = Subject.query.order_by(Subject.name).all()
    existing = {}
    if selected_class:
        items = Schedule.query.filter_by(class_name=selected_class).all()
        for item in items:
            existing[(item.day_of_week, item.lesson_number)] = item

    return render_template('schedule_edit.html',
                           classes=classes, selected_class=selected_class,
                           subjects=subjects, existing=existing,
                           day_names=DAY_NAMES, max_lesson=MAX_LESSON)


# ---------- ДОМАШНИЕ ЗАДАНИЯ ----------

@app.route('/homework')
@login_required
@role_required('teacher', 'admin')
def homework_list():
    teacher = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])
    selected_class = request.args.get('class_name', classes[0] if classes else None)

    if teacher.role == 'teacher':
        subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    else:
        subjects = Subject.query.order_by(Subject.name).all()

    homeworks = []
    if selected_class:
        homeworks = Homework.query.filter_by(class_name=selected_class)\
            .order_by(Homework.date.desc()).all()

    return render_template('homework_list.html',
                           teacher=teacher, classes=classes,
                           selected_class=selected_class,
                           subjects=subjects, homeworks=homeworks)


@app.route('/homework/add', methods=['GET', 'POST'])
@login_required
@role_required('teacher', 'admin')
def homework_add():
    teacher = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    if teacher.role == 'teacher':
        subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    else:
        subjects = Subject.query.order_by(Subject.name).all()

    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        class_name = request.form.get('class_name', '').strip()
        date_str = request.form.get('date')
        text = request.form.get('text', '').strip()

        if not subject_id or not class_name or not text:
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('homework_add'))

        try:
            hw_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            hw_date = datetime.utcnow().date()

        db.session.add(Homework(
            subject_id=int(subject_id), class_name=class_name,
            date=hw_date, text=text, teacher_id=teacher.id
        ))
        db.session.commit()
        flash('Домашнее задание добавлено!', 'success')
        return redirect(url_for('homework_list', class_name=class_name))

    return render_template('homework_form.html',
                           homework=None, classes=classes, subjects=subjects)


@app.route('/homework/edit/<int:hw_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher', 'admin')
def homework_edit(hw_id):
    hw = Homework.query.get_or_404(hw_id)
    teacher = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    if teacher.role == 'teacher':
        subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    else:
        subjects = Subject.query.order_by(Subject.name).all()

    if request.method == 'POST':
        hw.subject_id = int(request.form.get('subject_id'))
        hw.class_name = request.form.get('class_name', '').strip()
        hw.text = request.form.get('text', '').strip()
        try:
            hw.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
        db.session.commit()
        flash('Задание обновлено', 'success')
        return redirect(url_for('homework_list', class_name=hw.class_name))

    return render_template('homework_form.html',
                           homework=hw, classes=classes, subjects=subjects)


@app.route('/homework/delete/<int:hw_id>', methods=['POST'])
@login_required
@role_required('teacher', 'admin')
def homework_delete(hw_id):
    hw = Homework.query.get_or_404(hw_id)
    class_name = hw.class_name
    db.session.delete(hw)
    db.session.commit()
    flash('Задание удалено', 'success')
    return redirect(url_for('homework_list', class_name=class_name))


# ---------- ОТЧЁТ ЗА ЧЕТВЕРТЬ ----------

@app.route('/report')
@login_required
@role_required('teacher', 'admin')
def report():
    user = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    selected_class = request.args.get('class_name', classes[0] if classes else None)
    current_year = datetime.utcnow().year
    selected_quarter = int(request.args.get('quarter', 2))
    selected_year = int(request.args.get('year', current_year))

    if user.role == 'teacher':
        subjects = Subject.query.filter_by(teacher_id=user.id)\
            .order_by(Subject.name).all()
    else:
        subjects = Subject.query.order_by(Subject.name).all()

    students = []
    if selected_class:
        students = User.query.filter_by(role='student', class_name=selected_class)\
            .order_by(User.full_name).all()

    start_date, end_date = get_quarter_dates(selected_quarter, selected_year)
    report_data = []

    for student in students:
        row = {'student': student, 'subjects': {},
               'attendance': {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}}

        for subject in subjects:
            grades = Grade.query.filter(
                Grade.student_id == student.id,
                Grade.subject_id == subject.id,
                Grade.date >= start_date,
                Grade.date <= end_date
            ).all()
            values = [g.value for g in grades]
            avg = round(sum(values) / len(values), 2) if values else None
            row['subjects'][subject.id] = {
                'grades': values, 'average': avg,
                'final': calculate_final_grade(avg)
            }

        for att in Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all():
            if att.mark in row['attendance']:
                row['attendance'][att.mark] += 1

        report_data.append(row)

    return render_template('report.html',
                           user=user, classes=classes,
                           selected_class=selected_class,
                           selected_quarter=selected_quarter,
                           selected_year=selected_year,
                           quarters=QUARTERS, subjects=subjects,
                           report_data=report_data,
                           start_date=start_date, end_date=end_date)


@app.route('/report/student/<int:student_id>')
@login_required
@role_required('teacher', 'admin')
def report_student(student_id):
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('Это не ученик', 'error')
        return redirect(url_for('report'))

    current_year = datetime.utcnow().year
    selected_year = int(request.args.get('year', current_year))
    quarters_data = []

    for q_num in range(1, 5):
        start_date, end_date = get_quarter_dates(q_num, selected_year)
        subjects_data = []

        for subject in Subject.query.order_by(Subject.name).all():
            grades = Grade.query.filter(
                Grade.student_id == student.id,
                Grade.subject_id == subject.id,
                Grade.date >= start_date,
                Grade.date <= end_date
            ).all()
            if grades:
                values = [g.value for g in grades]
                avg = round(sum(values) / len(values), 2)
                subjects_data.append({
                    'subject': subject, 'grades': values,
                    'average': avg, 'final': calculate_final_grade(avg)
                })

        att_stats = {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}
        for att in Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all():
            if att.mark in att_stats:
                att_stats[att.mark] += 1

        quarters_data.append({
            'quarter': q_num, 'name': QUARTERS[q_num]['name'],
            'start': start_date, 'end': end_date,
            'subjects': subjects_data, 'attendance': att_stats
        })

    return render_template('report_student.html',
                           student=student, quarters_data=quarters_data,
                           selected_year=selected_year, is_own=False)


@app.route('/report/print')
@login_required
@role_required('teacher', 'admin')
def report_print():
    user = User.query.get(session['user_id'])
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    selected_class = request.args.get('class_name', classes[0] if classes else None)
    current_year = datetime.utcnow().year
    selected_quarter = int(request.args.get('quarter', 2))
    selected_year = int(request.args.get('year', current_year))

    if user.role == 'teacher':
        subjects = Subject.query.filter_by(teacher_id=user.id)\
            .order_by(Subject.name).all()
    else:
        subjects = Subject.query.order_by(Subject.name).all()

    students = []
    if selected_class:
        students = User.query.filter_by(role='student', class_name=selected_class)\
            .order_by(User.full_name).all()

    start_date, end_date = get_quarter_dates(selected_quarter, selected_year)
    report_data = []

    for student in students:
        row = {'student': student, 'subjects': {},
               'attendance': {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}}

        for subject in subjects:
            grades = Grade.query.filter(
                Grade.student_id == student.id,
                Grade.subject_id == subject.id,
                Grade.date >= start_date,
                Grade.date <= end_date
            ).all()
            values = [g.value for g in grades]
            avg = round(sum(values) / len(values), 2) if values else None
            row['subjects'][subject.id] = {
                'average': avg, 'final': calculate_final_grade(avg)
            }

        for att in Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all():
            if att.mark in row['attendance']:
                row['attendance'][att.mark] += 1

        report_data.append(row)

    return render_template('report_print.html',
                           selected_class=selected_class,
                           selected_quarter=selected_quarter,
                           selected_year=selected_year,
                           quarters=QUARTERS, subjects=subjects,
                           report_data=report_data,
                           start_date=start_date, end_date=end_date)


@app.route('/my-report')
@login_required
@role_required('student')
def my_report():
    student = User.query.get(session['user_id'])
    current_year = datetime.utcnow().year
    selected_year = int(request.args.get('year', current_year))
    quarters_data = []

    for q_num in range(1, 5):
        start_date, end_date = get_quarter_dates(q_num, selected_year)
        subjects_data = []

        for subject in Subject.query.order_by(Subject.name).all():
            grades = Grade.query.filter(
                Grade.student_id == student.id,
                Grade.subject_id == subject.id,
                Grade.date >= start_date,
                Grade.date <= end_date
            ).all()
            if grades:
                values = [g.value for g in grades]
                avg = round(sum(values) / len(values), 2)
                subjects_data.append({
                    'subject': subject, 'grades': values,
                    'average': avg, 'final': calculate_final_grade(avg)
                })

        att_stats = {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}
        for att in Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all():
            if att.mark in att_stats:
                att_stats[att.mark] += 1

        quarters_data.append({
            'quarter': q_num, 'name': QUARTERS[q_num]['name'],
            'start': start_date, 'end': end_date,
            'subjects': subjects_data, 'attendance': att_stats
        })

    return render_template('report_student.html',
                           student=student, quarters_data=quarters_data,
                           selected_year=selected_year, is_own=True)


# ---------- ПЕЧАТЬ ДНЕВНИКА ----------

@app.route('/print-diary')
@login_required
@role_required('student')
def print_diary():
    student = User.query.get(session['user_id'])
    current_year = datetime.utcnow().year
    selected_year = int(request.args.get('year', current_year))
    selected_quarter = int(request.args.get('quarter', 2))
    start_date, end_date = get_quarter_dates(selected_quarter, selected_year)

    subjects_data = []
    for subject in Subject.query.order_by(Subject.name).all():
        grades = Grade.query.filter(
            Grade.student_id == student.id,
            Grade.subject_id == subject.id,
            Grade.date >= start_date,
            Grade.date <= end_date
        ).order_by(Grade.date).all()
        if grades:
            values = [g.value for g in grades]
            avg = round(sum(values) / len(values), 2)
            subjects_data.append({
                'subject': subject, 'grades': grades,
                'average': avg, 'final': calculate_final_grade(avg)
            })

    attendance_records = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).order_by(Attendance.date).all()

    att_stats = {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}
    for att in attendance_records:
        if att.mark in att_stats:
            att_stats[att.mark] += 1

    return render_template('print_diary.html',
                           student=student, subjects_data=subjects_data,
                           attendance_records=attendance_records,
                           att_stats=att_stats,
                           start_date=start_date, end_date=end_date,
                           selected_quarter=selected_quarter,
                           selected_year=selected_year,
                           quarters=QUARTERS, full=False)


@app.route('/print-diary/full')
@login_required
@role_required('student')
def print_diary_full():
    student = User.query.get(session['user_id'])

    subjects_data = []
    for subject in Subject.query.order_by(Subject.name).all():
        grades = Grade.query.filter(
            Grade.student_id == student.id,
            Grade.subject_id == subject.id
        ).order_by(Grade.date).all()
        if grades:
            values = [g.value for g in grades]
            avg = round(sum(values) / len(values), 2)
            subjects_data.append({
                'subject': subject, 'grades': grades,
                'average': avg, 'final': calculate_final_grade(avg)
            })

    attendance_records = Attendance.query.filter_by(student_id=student.id)\
        .order_by(Attendance.date).all()

    att_stats = {'Н': 0, 'О': 0, 'П': 0, 'Б': 0}
    for att in attendance_records:
        if att.mark in att_stats:
            att_stats[att.mark] += 1

    return render_template('print_diary.html',
                           student=student, subjects_data=subjects_data,
                           attendance_records=attendance_records,
                           att_stats=att_stats,
                           start_date=None, end_date=None,
                           selected_quarter=None,
                           selected_year=datetime.utcnow().year,
                           quarters=QUARTERS, full=True)


# ============ АДМИН-ПАНЕЛЬ ============

@app.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    students = User.query.filter_by(role='student')\
        .order_by(User.class_name, User.full_name).all()
    teachers = User.query.filter_by(role='teacher')\
        .order_by(User.full_name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    return render_template('admin_panel.html',
                           students=students, teachers=teachers,
                           subjects=subjects, classes=classes,
                           total_students=len(students),
                           total_teachers=len(teachers),
                           total_subjects=len(subjects))


@app.route('/admin/student/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_student():
    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        class_name = request.form.get('class_name', '').strip()

        if not all([username, password, full_name, class_name]):
            flash('Все поля обязательны', 'error')
            return redirect(url_for('admin_add_student'))

        if User.query.filter_by(username=username).first():
            flash('Такой логин уже занят', 'error')
            return redirect(url_for('admin_add_student'))

        student = User(username=username, full_name=full_name,
                       role='student', class_name=class_name)
        student.set_password(password)
        db.session.add(student)
        db.session.commit()
        flash(f'Ученик {full_name} добавлен!', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_student_form.html', student=None, classes=classes)


@app.route('/admin/student/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_student(student_id):
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('Это не ученик', 'error')
        return redirect(url_for('admin_panel'))

    classes = sorted([c[0] for c in db.session.query(User.class_name)
                      .filter(User.role == 'student', User.class_name.isnot(None))
                      .distinct().all()])

    if request.method == 'POST':
        student.full_name = request.form.get('full_name', '').strip()
        student.class_name = request.form.get('class_name', '').strip()
        new_password = request.form.get('password', '').strip()
        if new_password:
            student.set_password(new_password)
        db.session.commit()
        flash(f'Данные {student.full_name} обновлены', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_student_form.html', student=student, classes=classes)


@app.route('/admin/student/delete/<int:student_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_student(student_id):
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('Это не ученик', 'error')
        return redirect(url_for('admin_panel'))
    name = student.full_name
    Grade.query.filter_by(student_id=student.id).delete()
    Attendance.query.filter_by(student_id=student.id).delete()
    db.session.delete(student)
    db.session.commit()
    flash(f'Ученик {name} удалён', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/teacher/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_teacher():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()

        if not all([username, password, full_name]):
            flash('Все поля обязательны', 'error')
            return redirect(url_for('admin_add_teacher'))

        if User.query.filter_by(username=username).first():
            flash('Такой логин уже занят', 'error')
            return redirect(url_for('admin_add_teacher'))

        teacher = User(username=username, full_name=full_name, role='teacher')
        teacher.set_password(password)
        db.session.add(teacher)
        db.session.commit()
        flash(f'Учитель {full_name} добавлен!', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_teacher_form.html', teacher=None)


@app.route('/admin/teacher/edit/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_teacher(teacher_id):
    teacher = User.query.get_or_404(teacher_id)
    if teacher.role != 'teacher':
        flash('Это не учитель', 'error')
        return redirect(url_for('admin_panel'))

    if request.method == 'POST':
        teacher.full_name = request.form.get('full_name', '').strip()
        new_password = request.form.get('password', '').strip()
        if new_password:
            teacher.set_password(new_password)
        db.session.commit()
        flash(f'Данные {teacher.full_name} обновлены', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_teacher_form.html', teacher=teacher)


@app.route('/admin/teacher/delete/<int:teacher_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_teacher(teacher_id):
    teacher = User.query.get_or_404(teacher_id)
    if teacher.role != 'teacher':
        flash('Это не учитель', 'error')
        return redirect(url_for('admin_panel'))

    if Subject.query.filter_by(teacher_id=teacher.id).first():
        flash('Нельзя удалить: у учителя есть предметы', 'error')
        return redirect(url_for('admin_panel'))

    name = teacher.full_name
    db.session.delete(teacher)
    db.session.commit()
    flash(f'Учитель {name} удалён', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/subject/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_add_subject():
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        teacher_id = request.form.get('teacher_id', '').strip()

        if not name:
            flash('Название предмета обязательно', 'error')
            return redirect(url_for('admin_add_subject'))

        subject = Subject(name=name,
                          teacher_id=int(teacher_id) if teacher_id else None)
        db.session.add(subject)
        db.session.commit()
        flash(f'Предмет "{name}" добавлен!', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_subject_form.html', subject=None, teachers=teachers)


@app.route('/admin/subject/edit/<int:subject_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_edit_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()

    if request.method == 'POST':
        subject.name = request.form.get('name', '').strip()
        teacher_id = request.form.get('teacher_id', '').strip()
        subject.teacher_id = int(teacher_id) if teacher_id else None
        db.session.commit()
        flash(f'Предмет "{subject.name}" обновлён', 'success')
        return redirect(url_for('admin_panel'))

    return render_template('admin_subject_form.html', subject=subject, teachers=teachers)


@app.route('/admin/subject/delete/<int:subject_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)

    if Grade.query.filter_by(subject_id=subject.id).count() > 0:
        flash('Нельзя удалить: по предмету есть оценки', 'error')
        return redirect(url_for('admin_panel'))

    name = subject.name
    db.session.delete(subject)
    db.session.commit()
    flash(f'Предмет "{name}" удалён', 'success')
    return redirect(url_for('admin_panel'))


# ============ ИНИЦИАЛИЗАЦИЯ БД ============

def init_db():
    with app.app_context():
        db.create_all()

        if not User.query.first():
            admin = User(username='admin', full_name='Администратор школы', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

            teacher1 = User(username='teacher', full_name='Иванова Мария Петровна', role='teacher')
            teacher1.set_password('teacher123')
            teacher2 = User(username='teacher2', full_name='Петров Сергей Иванович', role='teacher')
            teacher2.set_password('teacher123')
            db.session.add_all([teacher1, teacher2])
            db.session.commit()

            math = Subject(name='Математика', teacher_id=teacher1.id)
            rus = Subject(name='Русский язык', teacher_id=teacher1.id)
            phys = Subject(name='Физика', teacher_id=teacher2.id)
            db.session.add_all([math, rus, phys])
            db.session.commit()

            student1 = User(username='student', full_name='Сидоров Алексей', role='student', class_name='5А')
            student1.set_password('student123')
            student2 = User(username='student2', full_name='Кузнецова Анна', role='student', class_name='5А')
            student2.set_password('student123')
            student3 = User(username='student3', full_name='Морозов Дмитрий', role='student', class_name='5Б')
            student3.set_password('student123')
            db.session.add_all([student1, student2, student3])
            db.session.commit()

            today = datetime.utcnow().date()
            grades = [
                Grade(student_id=student1.id, subject_id=math.id, value=5, date=today - timedelta(days=1), comment='Отличная работа'),
                Grade(student_id=student1.id, subject_id=math.id, value=4, date=today - timedelta(days=3)),
                Grade(student_id=student1.id, subject_id=rus.id, value=5, date=today - timedelta(days=2), comment='Сочинение'),
                Grade(student_id=student1.id, subject_id=phys.id, value=3, date=today - timedelta(days=5)),
                Grade(student_id=student1.id, subject_id=rus.id, value=4, date=today),
                Grade(student_id=student2.id, subject_id=math.id, value=5, date=today - timedelta(days=1)),
                Grade(student_id=student2.id, subject_id=rus.id, value=5, date=today - timedelta(days=2)),
                Grade(student_id=student2.id, subject_id=phys.id, value=4, date=today),
                Grade(student_id=student3.id, subject_id=math.id, value=3, date=today),
                Grade(student_id=student3.id, subject_id=rus.id, value=4, date=today - timedelta(days=1)),
            ]
            db.session.add_all(grades)
            db.session.commit()

            attendance_samples = [
                Attendance(student_id=student1.id, date=today, mark='Н', comment='Прогул 3 урока', teacher_id=teacher1.id),
                Attendance(student_id=student1.id, date=today - timedelta(days=2), mark='О', comment='Опоздал на 15 мин', teacher_id=teacher1.id),
                Attendance(student_id=student1.id, date=today - timedelta(days=4), mark='Б', comment='ОРВИ', teacher_id=teacher1.id),
                Attendance(student_id=student2.id, date=today - timedelta(days=1), mark='Б', comment='ОРВИ', teacher_id=teacher1.id),
                Attendance(student_id=student2.id, date=today, mark='П', comment='Справка', teacher_id=teacher1.id),
                Attendance(student_id=student3.id, date=today - timedelta(days=3), mark='Н', comment='Прогул', teacher_id=teacher1.id),
            ]
            db.session.add_all(attendance_samples)
            db.session.commit()

            schedule_samples = [
                Schedule(class_name='5А', day_of_week=1, lesson_number=1, subject_id=math.id, room='101', time_start='08:30', time_end='09:15'),
                Schedule(class_name='5А', day_of_week=1, lesson_number=2, subject_id=rus.id,  room='102', time_start='09:25', time_end='10:10'),
                Schedule(class_name='5А', day_of_week=1, lesson_number=3, subject_id=phys.id, room='103', time_start='10:25', time_end='11:10'),
                Schedule(class_name='5А', day_of_week=2, lesson_number=1, subject_id=rus.id,  room='102', time_start='08:30', time_end='09:15'),
                Schedule(class_name='5А', day_of_week=2, lesson_number=2, subject_id=math.id, room='101', time_start='09:25', time_end='10:10'),
                Schedule(class_name='5А', day_of_week=3, lesson_number=1, subject_id=phys.id, room='103', time_start='08:30', time_end='09:15'),
                Schedule(class_name='5А', day_of_week=3, lesson_number=2, subject_id=math.id, room='101', time_start='09:25', time_end='10:10'),
                Schedule(class_name='5А', day_of_week=4, lesson_number=1, subject_id=math.id, room='101', time_start='08:30', time_end='09:15'),
                Schedule(class_name='5А', day_of_week=5, lesson_number=1, subject_id=rus.id,  room='102', time_start='08:30', time_end='09:15'),
                Schedule(class_name='5А', day_of_week=5, lesson_number=2, subject_id=phys.id, room='103', time_start='09:25', time_end='10:10'),
            ]
            db.session.add_all(schedule_samples)
            db.session.commit()

            homework_samples = [
                Homework(subject_id=math.id, class_name='5А', date=today, text='Параграф 12, задачи 1-5', teacher_id=teacher1.id),
                Homework(subject_id=rus.id, class_name='5А', date=today, text='Упражнение 45, выучить правило', teacher_id=teacher1.id),
                Homework(subject_id=phys.id, class_name='5А', date=today + timedelta(days=1), text='Параграф 8, ответить на вопросы', teacher_id=teacher2.id),
            ]
            db.session.add_all(homework_samples)
            db.session.commit()

            print("=" * 55)
            print("✅ База данных инициализирована!")
            print("=" * 55)


# Инициализация БД при старте (важно для Render)
with app.app_context():
    init_db()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
