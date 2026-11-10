"""Isolated Kanban browser fixtures, without background workers or outbound mail."""
import os,secrets
os.environ.update(PORTAL_BASE_URL='http://127.0.0.1:8767',PORTAL_SECRET_KEY='board-test-secret-at-least-32-characters',JWT_APP_SECRET='board-test-jwt-at-least-32-characters')
from app import main
from app.db import init_db,SessionLocal,User,set_setting,Vote
from app.security import hash_password
init_db()
with SessionLocal() as db:
    set_setting(db,'module_tasks','1')
    for name,email,permission in [('Mara Planung','owner@example.org','tasks'),('Alex Mitarbeit','editor@example.org',''),('Sam Lesen','reader@example.org','')]:
        db.add(User(name=name,email=email,password_hash=hash_password('board-browser-password'),permissions=permission))
    db.flush()
    owner=db.query(User).filter(User.email=='owner@example.org').one()
    db.add(Vote(owner_id=owner.id,title='Teamentscheidung',public_token=secrets.token_hex(20)))
    db.commit()
# Synthetic dense board for layout/performance acceptance.
from app import task_boards as boards,tasks
from app.task_models import TaskBoard,TaskBoardColumn,TaskCheck,TaskComment
with SessionLocal() as db:
    owner=db.query(User).filter(User.email=='owner@example.org').one()
    board=TaskBoard(owner_id=owner.id,title='Dichtes Teamboard',mode='free');db.add(board);db.flush()
    columns=[]
    for index,title in enumerate(['Ideenspeicher','In Planung','In Arbeit','Erledigt']):
        col=TaskBoardColumn(board_id=board.id,title=title,status='',position=index);db.add(col);columns.append(col)
    db.flush()
    for index in range(48):
        kind=list(boards.CARD_TYPES)[index%6]
        task=tasks.create(db,owner,dict(title=f'{boards.CARD_TYPES[kind]}: Teamplanung {index+1}',assignee_id=str(owner.id),tags='Team, Planung' if index%3==0 else '',description='Synthetischer Inhalt zur Layoutprüfung.' if index%4==0 else ''))
        card=boards.add_native(db,owner,board,columns[index//12],task)
        card.card_type=kind;card.cover_color='blue' if index%5==0 else ''
        if index%3==0:
            db.add(TaskCheck(task_id=task.id,title='Synthetischer Prüfschritt',done=index%2==0))
            db.add(TaskComment(task_id=task.id,author_id=owner.id,body='Synthetischer Kommentar.'))
    db.commit()
app=main.app
