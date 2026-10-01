"""
Admin Blueprint.

Routes:
  GET        /admin                          — dashboard
  GET        /admin/stats                    — JSON: 7-day trend + today stats
  GET        /admin/students                 — student list
  GET/POST   /admin/student/edit/<id>        — edit student
  POST       /admin/student/delete/<id>      — delete student
  GET/POST   /admin/mark                     — manual attendance marking
  GET        /admin/view_images              — attendance image viewer
  GET        /admin/users                    — user list
  GET/POST   /admin/user/edit/<id>           — edit user
  POST       /admin/user/delete/<id>         — delete user
"""

from datetime import datetime, timedelta
import os

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from src.utils.db import supabase_admin as supabase, is_valid_email
from src import config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _require_admin():
    """Return a redirect/render when the current user is not admin, else None."""
    if not session.get('is_admin'):
        return render_template('login.html', error="Admin access required")
    return None


@admin_bp.route('')
@admin_bp.route('/')
def admin_dashboard():
    denied = _require_admin()
    if denied:
        return denied

    try:
        total_students = supabase.table('students').select('*', count='exact').execute().count or 0
        total_attendance = supabase.table('attendance').select('*', count='exact').execute().count or 0
        
        # We can't efficiently count auth.users from client without admin API, so we fetch all
        users_resp = supabase.auth.admin.list_users()
        total_users = len(users_resp) if isinstance(users_resp, list) else len(getattr(users_resp, 'users', []))
        
        today_date = datetime.now().strftime("%Y-%m-%d")
        
        # Count attendance where timestamp starts with today's date
        today_att_resp = supabase.table('attendance').select('*', count='exact').ilike('timestamp', f'{today_date}%').execute()
        today_att = today_att_resp.count or 0
    except Exception as e:
        print("Dashboard error:", e)
        total_students, total_attendance, total_users, today_att = 0, 0, 0, 0

    return render_template(
        'admin_dashboard.html',
        total_students=total_students,
        total_attendance=total_attendance,
        total_users=total_users,
        today_attendance=today_att,
    )


@admin_bp.route('/stats')
def admin_stats():
    if not session.get('is_admin'):
        return jsonify({'error': 'admin required'}), 403

    trend = []
    try:
        for d in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d")
            
            cnt_resp = supabase.table('attendance').select('*', count='exact').ilike('timestamp', f'{day}%').execute()
            cnt = cnt_resp.count or 0
            trend.append({'date': day, 'count': cnt})

        today = datetime.now().strftime("%Y-%m-%d")
        present_resp = supabase.table('attendance').select('*', count='exact').ilike('timestamp', f'{today}%').ilike('status', '%Present%').execute()
        present = present_resp.count or 0
        
        total_today_resp = supabase.table('attendance').select('*', count='exact').ilike('timestamp', f'{today}%').execute()
        total_today = total_today_resp.count or 0
        
    except Exception as e:
        print("Stats error:", e)
        present = 0
        total_today = 0

    return jsonify({'trend': trend, 'present': present, 'absent': max(total_today - present, 0)})


@admin_bp.route('/students')
def admin_students():
    denied = _require_admin()
    if denied:
        return denied

    try:
        students_resp = supabase.table('students').select('*').order('name').execute()
        students = students_resp.data
    except Exception:
        students = []
        
    return render_template('admin_students.html', students=students)


@admin_bp.route('/student/edit/<student_id>', methods=['GET', 'POST'])
def admin_edit_student(student_id):
    denied = _require_admin()
    if denied:
        return denied

    try:
        student_resp = supabase.table('students').select('*').eq('id', student_id).execute()
        if not student_resp.data:
            return redirect(url_for('admin.admin_students'))
        student = student_resp.data[0]
    except Exception:
        return redirect(url_for('admin.admin_students'))

    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        program = request.form.get('program', '').strip()
        branch  = request.form.get('branch', '').strip()
        enrollment_year = request.form.get('enrollment_year', '').strip()
        gmail   = request.form.get('gmail', '').strip()
        photo   = request.files.get('photo')

        if not name or not program or not branch or not gmail:
            return redirect(url_for('admin.admin_students'))
        if not is_valid_email(gmail):
            return redirect(url_for('admin.admin_students'))

        update_payload = {
            'name': name,
            'program': program,
            'branch': branch,
            'gmail': gmail
        }
        if enrollment_year:
            try:
                update_payload['enrollment_year'] = int(enrollment_year)
            except ValueError:
                pass

        # If a new re-enrollment photo is provided, encode it and reset EWMA
        if photo and photo.filename:
            from werkzeug.utils import secure_filename
            import os
            import cv2
            import numpy as np
            from src.utils.face import model, normalize_embedding

            safe_id = secure_filename(student_id)
            if safe_id:
                filename = f"{safe_id}.jpg"
                os.makedirs(config.KNOWN_FACES_DIR, exist_ok=True)
                filepath = os.path.join(config.KNOWN_FACES_DIR, filename)
                photo.save(filepath)

                image = cv2.imread(filepath)
                if image is not None:
                    faces = model.get(image)
                    if faces:
                        face = faces[0]
                        new_emb = np.array(face.embedding, dtype=np.float32)
                        normalized_emb = normalize_embedding(new_emb)
                        if normalized_emb is not None:
                            update_payload['embedding'] = normalized_emb.tolist()
                            update_payload['current_ewma_drift'] = 0.0
                            update_payload['drift_alert_level'] = 'HEALTHY'
                            _new_cache_embedding = normalized_emb

                            # Log re-enrollment event
                            try:
                                supabase.table('embedding_health').insert({
                                    'student_id': student_id,
                                    'drift_score': 0.0,
                                    'ewma_drift': 0.0,
                                    'match_confidence': 1.0,
                                    'alert_level': 'RE_ENROLLED',
                                    'pose_yaw': 0.0,
                                    'pose_pitch': 0.0,
                                    'pose_accepted': True
                                }).execute()
                            except Exception as err:
                                print(f"Error logging re-enrollment event: {err}")

        try:
            supabase.table('students').update(update_payload).eq('id', student_id).execute()
            # Keep in-memory face cache in sync (re-enrollment photo or metadata change)
            try:
                from src.utils.face_cache import add_student_to_cache
                cache_emb = locals().get('_new_cache_embedding')
                if cache_emb is not None:
                    add_student_to_cache(
                        student_id=student_id, name=name,
                        program=program, branch=branch, embedding=cache_emb,
                    )
                else:
                    from src.utils.face_cache import reload_face_cache
                    reload_face_cache()
            except Exception:
                pass
        except Exception as e:
            print("Update student error:", e)
            
        return redirect(url_for('admin.admin_drift'))

    return render_template('edit_student.html', student=student)


@admin_bp.route('/student/delete/<student_id>', methods=['POST'])
def admin_delete_student(student_id):
    denied = _require_admin()
    if denied:
        return denied

    try:
        # 1. Delete student attendance logs first to satisfy foreign key constraints
        supabase.table('attendance').delete().eq('student_id', student_id).execute()
        
        # 2. Delete the student profile from the database
        supabase.table('students').delete().eq('id', student_id).execute()
        
        # 3. Clean up the registered photo from disk
        from werkzeug.utils import secure_filename
        safe_id = secure_filename(student_id)
        if safe_id:
            filename = f"{safe_id}.jpg"
            filepath = os.path.join(config.KNOWN_FACES_DIR, filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        # 4. Evict from in-memory face cache so deleted students stop matching
        try:
            from src.utils.face_cache import remove_student_from_cache
            remove_student_from_cache(student_id)
        except Exception:
            pass
    except Exception as e:
        print(f"Cascading delete failed for student {student_id}: {e}")
        
    return redirect(url_for('admin.admin_students'))


@admin_bp.route('/mark', methods=['GET', 'POST'])
def admin_mark_attendance():
    denied = _require_admin()
    if denied:
        return denied

    try:
        students_resp = supabase.table('students').select('*').order('name').execute()
        students = students_resp.data or []
    except Exception:
        students = []

    if request.method == 'POST':
        present_ids = set(request.form.getlist('student_ids'))
        lecture     = request.form.get('lecture', '').strip()
        timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not lecture:
            return render_template('admin_mark.html', students=students, error="Lecture name is required")

        attendance_records = []
        for s in students:
            s_id = s.get('id')
            status = 'Present' if s_id in present_ids else 'Absent'
            attendance_records.append({
                "student_id": s_id,
                "name": s.get('name'),
                "program": s.get('program'),
                "branch": s.get('branch'),
                "status": status,
                "timestamp": timestamp,
                "lecture": lecture
            })

        # Auto-register new lecture names so lecture dropdowns stay populated
        # (additive only — failures are ignored and never block marking)
        try:
            ex_l = supabase.table('academic_structure').select('id').eq('type', 'lecture').eq('value', lecture).execute()
            if not ex_l.data:
                supabase.table('academic_structure').insert({"type": "lecture", "value": lecture}).execute()
        except Exception:
            pass

        try:
            if attendance_records:
                supabase.table('attendance').insert(attendance_records).execute()
        except Exception as e:
            print("Bulk manual mark attendance error:", e)
            return render_template('admin_mark.html', students=students, error="Database error")
            
        return redirect(url_for('admin.admin_dashboard'))

    return render_template('admin_mark.html', students=students)


@admin_bp.route('/view_images')
def view_images():
    denied = _require_admin()
    if denied:
        return denied
    return render_template('view_images.html')


@admin_bp.route('/users')
def admin_users():
    denied = _require_admin()
    if denied:
        return denied

    try:
        users_resp = supabase.auth.admin.list_users()
        users_list = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', [])
        users = []
        for u in users_list:
            metadata = u.user_metadata or {}
            users.append({
                'id': u.id,
                'email': u.email,
                'username': metadata.get('username', u.email),
                'is_admin': metadata.get('is_admin', False)
            })
        
        # Sort users by username case-insensitive
        users.sort(key=lambda x: x['username'].lower())
    except Exception as e:
        print("List users error:", e)
        users = []
        
    return render_template('admin_users.html', users=users, current_user=session.get('username'))


@admin_bp.route('/user/edit/<user_id>', methods=['GET', 'POST'])
def admin_edit_user(user_id):
    denied = _require_admin()
    if denied:
        return denied

    try:
        user_resp = supabase.auth.admin.get_user_by_id(user_id)
        u = user_resp.user
        metadata = u.user_metadata or {}
        user = {
            'id': u.id,
            'email': u.email,
            'username': metadata.get('username', u.email),
            'is_admin': metadata.get('is_admin', False)
        }
    except Exception:
        return redirect(url_for('admin.admin_users'))

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email    = request.form.get('email', '').strip()
        new_is_admin = 1 if request.form.get('is_admin') else 0
        new_password = request.form.get('password', '').strip()

        if not new_username:
            return render_template('admin_edit_user.html', user=user,
                                   error="Username is required.",
                                   current_user=session.get('username'))

        if new_email and not is_valid_email(new_email):
            return render_template('admin_edit_user.html', user=user,
                                   error="Enter a valid email address.",
                                   current_user=session.get('username'))

        # Prevent removing admin rights from the last admin
        if user['is_admin'] and not new_is_admin:
            try:
                # Count admins
                all_users_resp = supabase.auth.admin.list_users()
                users_list = all_users_resp if isinstance(all_users_resp, list) else getattr(all_users_resp, 'users', [])
                admin_count = sum(1 for u in users_list if (u.user_metadata or {}).get('is_admin', False))
                
                if admin_count <= 1:
                    return render_template('admin_edit_user.html', user=user,
                                        error="Cannot revoke the last admin account.",
                                        current_user=session.get('username'))
            except Exception:
                pass

        try:
            update_data = {
                "email": new_email if new_email else user['email'],
                "user_metadata": {
                    "username": new_username,
                    "is_admin": bool(new_is_admin)
                }
            }
            if new_password:
                if len(new_password) < config.MIN_PASSWORD_LENGTH:
                    return render_template('admin_edit_user.html', user=user,
                                           error=f"Password must be >= {config.MIN_PASSWORD_LENGTH} chars.",
                                           current_user=session.get('username'))
                update_data["password"] = new_password
                
            supabase.auth.admin.update_user_by_id(user_id, update_data)
        except Exception as e:
            return render_template('admin_edit_user.html', user=user,
                                   error="Error updating user: " + str(e),
                                   current_user=session.get('username'))

        return redirect(url_for('admin.admin_users'))

    return render_template('admin_edit_user.html', user=user, current_user=session.get('username'))


@admin_bp.route('/user/delete/<user_id>', methods=['POST'])
def admin_delete_user(user_id):
    denied = _require_admin()
    if denied:
        return denied

    # Don't allow user to delete themselves
    if session.get('user_id') == user_id:
        return redirect(url_for('admin.admin_users'))

    try:
        user_resp = supabase.auth.admin.get_user_by_id(user_id)
        u = user_resp.user
        
        # Prevent deleting the last admin
        if (u.user_metadata or {}).get('is_admin', False):
            all_users_resp = supabase.auth.admin.list_users()
            users_list = all_users_resp if isinstance(all_users_resp, list) else getattr(all_users_resp, 'users', [])
            admin_count = sum(1 for u in users_list if (u.user_metadata or {}).get('is_admin', False))
            if admin_count <= 1:
                return redirect(url_for('admin.admin_users'))

        supabase.auth.admin.delete_user(user_id)
    except Exception:
        pass

    return redirect(url_for('admin.admin_users'))


@admin_bp.route('/reset', methods=['POST'])
def admin_reset():
    denied = _require_admin()
    if denied:
        return denied

    reset_type = request.form.get('reset_type')
    if reset_type not in ('attendance', 'all'):
        return redirect(url_for('admin.admin_dashboard', error="Invalid reset type"))

    try:
        if reset_type == 'attendance':
            # Delete all rows in attendance table where att_id is greater than 0
            supabase.table('attendance').delete().gt('att_id', 0).execute()
        elif reset_type == 'all':
            # Delete attendance first because of foreign key dependency
            supabase.table('attendance').delete().gt('att_id', 0).execute()
            # Delete all students (where ID is not empty)
            supabase.table('students').delete().neq('id', '').execute()

            # Empty the known_faces directory
            if os.path.exists(config.KNOWN_FACES_DIR):
                for filename in os.listdir(config.KNOWN_FACES_DIR):
                    file_path = os.path.join(config.KNOWN_FACES_DIR, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        print(f"Failed to delete {file_path} on disk: {e}")
        else:
            return redirect(url_for('admin.admin_dashboard', error="Invalid reset type"))

        # Keep in-memory face cache consistent after destructive resets
        try:
            from src.utils.face_cache import reload_face_cache
            reload_face_cache()
        except Exception:
            pass

        return redirect(url_for('admin.admin_dashboard', status="success", message="Database reset successfully"))
    except Exception as e:
        print("Reset error:", e)
        return redirect(url_for('admin.admin_dashboard', error=str(e)))


@admin_bp.route('/academics', methods=['GET', 'POST'])
def admin_academics():
    denied = _require_admin()
    if denied:
        return denied

    if request.method == 'POST':
        action = request.form.get('action')
        item_type = request.form.get('type')  # program, branch, lecture, batch
        item_value = request.form.get('value', '').strip()

        from src.utils.academic_defaults import (
            ALLOWED_ACADEMIC_TYPES, DEFAULT_BRANCHES, DEFAULT_LECTURES, DEFAULT_PROGRAMS, DEFAULT_BATCHES,
            get_saved_batches, save_custom_batch, delete_custom_batch
        )

        if action == 'seed_defaults':
            # One-click restore of built-in COER defaults (additive: upsert only)
            try:
                for p in DEFAULT_PROGRAMS:
                    supabase.table('academic_structure').upsert(
                        {'type': 'program', 'value': p}, on_conflict='type,value').execute()
                for b in DEFAULT_BRANCHES:
                    supabase.table('academic_structure').upsert(
                        {'type': 'branch', 'value': b}, on_conflict='type,value').execute()
                for lec in DEFAULT_LECTURES:
                    supabase.table('academic_structure').upsert(
                        {'type': 'lecture', 'value': lec}, on_conflict='type,value').execute()
                for yr in DEFAULT_BATCHES:
                    try:
                        supabase.table('academic_structure').upsert(
                            {'type': 'batch', 'value': str(yr)}, on_conflict='type,value').execute()
                    except Exception:
                        save_custom_batch(str(yr))
            except Exception as e:
                print("Error seeding academic defaults:", e)
            return redirect(url_for('admin.admin_academics'))

        if action == 'add' and item_type and item_value:
            if item_type not in ALLOWED_ACADEMIC_TYPES:
                return redirect(url_for('admin.admin_academics'))
            if item_type == 'batch':
                try:
                    supabase.table('academic_structure').upsert({
                        'type': 'batch',
                        'value': item_value
                    }, on_conflict='type,value').execute()
                except Exception:
                    pass
                save_custom_batch(item_value)
            else:
                try:
                    supabase.table('academic_structure').upsert({
                        'type': item_type,
                        'value': item_value
                    }, on_conflict='type,value').execute()
                except Exception as e:
                    print("Error adding academic item:", e)

        elif action == 'delete' and item_type and item_value:
            if item_type not in ALLOWED_ACADEMIC_TYPES:
                return redirect(url_for('admin.admin_academics'))
            if item_type == 'batch':
                try:
                    supabase.table('academic_structure').delete().eq('type', 'batch').eq('value', item_value).execute()
                except Exception:
                    pass
                delete_custom_batch(item_value)
            else:
                try:
                    supabase.table('academic_structure').delete().eq('type', item_type).eq('value', item_value).execute()
                except Exception as e:
                    print("Error deleting academic item from academic_structure:", e)

        return redirect(url_for('admin.admin_academics'))

    # Fetch academic structure from table
    try:
        resp = supabase.table('academic_structure').select('*').order('value').execute()
        rows = resp.data or []
    except Exception:
        rows = []

    programs = sorted(list({r['value'] for r in rows if r.get('type') == 'program' and r.get('value')}))
    branches = sorted(list({r['value'] for r in rows if r.get('type') == 'branch' and r.get('value')}))
    lectures = sorted(list({r['value'] for r in rows if r.get('type') == 'lecture' and r.get('value')}))
    stored_batches = [r['value'] for r in rows if r.get('type') == 'batch' and r.get('value')]

    from src.utils.academic_defaults import (
        DEFAULT_BRANCHES, DEFAULT_LECTURES, DEFAULT_PROGRAMS, DEFAULT_BATCHES, get_saved_batches
    )

    # Batches / Years: union of DB batches + saved custom batches + student enrollment years + defaults
    batch_candidates = set()
    for b in stored_batches:
        if b:
            batch_candidates.add(str(b).strip())
    try:
        students_resp = supabase.table('students').select('enrollment_year').execute()
        for s in (students_resp.data or []):
            ey = s.get('enrollment_year')
            if ey:
                batch_candidates.add(str(ey).strip())
    except Exception:
        pass
    for b in get_saved_batches():
        if b:
            batch_candidates.add(str(b).strip())
    for b in DEFAULT_BATCHES:
        if b:
            batch_candidates.add(str(b).strip())

    def _sort_batch_key(v):
        try:
            return (0, int(v))
        except ValueError:
            return (1, str(v))

    batches_for_display = sorted(list(batch_candidates), key=_sort_batch_key, reverse=True)

    # Fallback so the page never renders completely empty on a fresh DB
    show_defaults_hint = not programs or not branches or not lectures
    programs_for_display = programs or list(DEFAULT_PROGRAMS)
    branches_for_display = branches or list(DEFAULT_BRANCHES)
    lectures_for_display = lectures or list(DEFAULT_LECTURES)

    return render_template(
        'admin_academics.html',
        programs=programs_for_display,
        branches=branches_for_display,
        batches=batches_for_display,
        lectures=lectures_for_display,
        programs_display=programs_for_display,
        branches_display=branches_for_display,
        batches_display=batches_for_display,
        lectures_display=lectures_for_display,
        show_defaults_hint=show_defaults_hint,
    )


# ---------------------------------------------------------------------------
# Biometric Drift Monitoring Dashboard (Patent Idea #3)
# ---------------------------------------------------------------------------

@admin_bp.route('/drift')
def admin_drift():
    """Biometric Drift Monitoring Dashboard."""
    denied = _require_admin()
    if denied:
        return denied

    try:
        # Fetch all students sorted by EWMA drift descending (most critical first)
        students_resp = supabase.table('students') \
            .select('id, name, program, branch, current_ewma_drift, drift_alert_level') \
            .order('current_ewma_drift', desc=True) \
            .execute()
        students = students_resp.data or []

        # Count summary stats
        summary = {
            'total': len(students),
            'healthy': sum(1 for s in students if (s.get('drift_alert_level') or 'HEALTHY') == 'HEALTHY'),
            'warning': sum(1 for s in students if s.get('drift_alert_level') == 'WARNING'),
            'critical': sum(1 for s in students if s.get('drift_alert_level') == 'CRITICAL'),
            'alert': sum(1 for s in students if s.get('drift_alert_level') == 'ALERT'),
        }
    except Exception as e:
        print("Error loading drift dashboard:", e)
        students = []
        summary = {'total': 0, 'healthy': 0, 'warning': 0, 'critical': 0, 'alert': 0}

    return render_template(
        'admin_drift.html',
        students=students,
        summary=summary,
        config=config
    )


@admin_bp.route('/api/drift_history/<student_id>')
def api_drift_history(student_id):
    """JSON API endpoint returning historical drift log events for a student."""
    denied = _require_admin()
    if denied:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        logs_resp = supabase.table('embedding_health') \
            .select('*') \
            .eq('student_id', student_id) \
            .order('created_at', desc=False) \
            .limit(50) \
            .execute()
        return jsonify({'success': True, 'data': logs_resp.data or []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/student/reset_drift/<student_id>', methods=['POST'])
def reset_student_drift(student_id):
    """Reset EWMA drift score to 0.00 upon re-enrollment."""
    denied = _require_admin()
    if denied:
        return denied

    try:
        # Reset current_ewma_drift and status in students table
        supabase.table('students').update({
            'current_ewma_drift': 0.0,
            'drift_alert_level': 'HEALTHY'
        }).eq('id', student_id).execute()

        # Append re-enrollment event to health log
        supabase.table('embedding_health').insert({
            'student_id': student_id,
            'drift_score': 0.0,
            'ewma_drift': 0.0,
            'match_confidence': 1.0,
            'alert_level': 'RE_ENROLLED',
            'pose_yaw': 0.0,
            'pose_pitch': 0.0,
            'pose_accepted': True
        }).execute()

    except Exception as e:
        print(f"Error resetting drift for {student_id}: {e}")

    return redirect(url_for('admin.admin_drift'))


