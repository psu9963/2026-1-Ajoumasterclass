from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, CalendarEvent
from datetime import datetime, timedelta

calendar_bp = Blueprint('calendar', __name__)

@calendar_bp.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html', active_menu='calendar')


# ── 일정 전체 조회 (FullCalendar용 JSON) ──────────────────
@calendar_bp.route('/api/calendar/events')
@login_required
def get_events():
    events = CalendarEvent.query.filter_by(user_id=current_user.id).all()

    COLOR_MAP = {
        'blue':   '#2563eb',
        'green':  '#16a34a',
        'red':    '#dc2626',
        'yellow': '#d97706',
        'purple': '#7c3aed',
        'pink':   '#db2777',
    }

    result = []
    for e in events:
        # 시작 datetime
        start = e.start_date
        if e.start_time:
            start += f'T{e.start_time}'

        # 종료 datetime
        end_date_raw = e.end_date or e.start_date
        if e.end_time:
            end = end_date_raw + f'T{e.end_time}'
        else:
            # FullCalendar는 all-day 이벤트의 end를 exclusive로 처리하므로
            # 사용자가 입력한 종료일 하루 전체가 표시되도록 +1일 보정
            end = (datetime.strptime(end_date_raw, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

        result.append({
            'id':              e.id,
            'title':           e.title,
            'start':           start,
            'end':             end,
            'backgroundColor': COLOR_MAP.get(e.color, '#2563eb'),
            'borderColor':     COLOR_MAP.get(e.color, '#2563eb'),
            'textColor':       '#ffffff',
            'extendedProps': {
                'description': e.description or '',
                'category':    e.category,
                'color':       e.color,
                'start_time':  e.start_time or '',
                'end_time':    e.end_time or '',
                'start_date':  e.start_date,
                'end_date':    e.end_date or '',
            }
        })
    return jsonify(result)


# ── 일정 추가 ──────────────────────────────────────────────
@calendar_bp.route('/api/calendar/events', methods=['POST'])
@login_required
def add_event():
    data = request.get_json()

    if not data.get('title') or not data.get('start_date'):
        return jsonify({'success': False, 'message': '제목과 날짜는 필수입니다.'}), 400

    event = CalendarEvent(
        user_id     = current_user.id,
        title       = data['title'],
        description = data.get('description', ''),
        start_date  = data['start_date'],
        end_date    = data.get('end_date', ''),
        start_time  = data.get('start_time', ''),
        end_time    = data.get('end_time', ''),
        color       = data.get('color', 'blue'),
        category    = data.get('category', '일반'),
        created_at  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({'success': True, 'id': event.id})


# ── 일정 수정 ──────────────────────────────────────────────
@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['PUT'])
@login_required
def update_event(event_id):
    event = CalendarEvent.query.filter_by(
        id=event_id, user_id=current_user.id
    ).first_or_404()

    data = request.get_json()
    event.title       = data.get('title', event.title)
    event.description = data.get('description', event.description)
    event.start_date  = data.get('start_date', event.start_date)
    event.end_date    = data.get('end_date', event.end_date)
    event.start_time  = data.get('start_time', event.start_time)
    event.end_time    = data.get('end_time', event.end_time)
    event.color       = data.get('color', event.color)
    event.category    = data.get('category', event.category)

    db.session.commit()
    return jsonify({'success': True})


# ── 일정 삭제 ──────────────────────────────────────────────
@calendar_bp.route('/api/calendar/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id):
    event = CalendarEvent.query.filter_by(
        id=event_id, user_id=current_user.id
    ).first_or_404()

    db.session.delete(event)
    db.session.commit()
    return jsonify({'success': True})
