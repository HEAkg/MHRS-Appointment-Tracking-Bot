import os.path
import threading
import time

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from gtts import gTTS
from playsound import playsound
from dotenv import load_dotenv
import bot

load_dotenv()

app = Flask(__name__)
app.secret_key = "12345"
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

DB_NAME = "appointments.db"
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
db = SQLAlchemy(app)
is_checking = False


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(11), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    authorization = db.Column(db.String(1000), nullable=True)
    appointment_requests = db.relationship('AppointmentRequest', backref='user')


class AppointmentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    city = db.Column(db.Integer, nullable=False)
    city_text = db.Column(db.String(50), nullable=False)
    district = db.Column(db.Integer, nullable=False)
    district_text = db.Column(db.String(50), nullable=False)
    clinic = db.Column(db.Integer, nullable=False)
    clinic_text = db.Column(db.String(200), nullable=False)
    hospital = db.Column(db.Integer, nullable=False)
    hospital_text = db.Column(db.String(200), nullable=False)
    examination = db.Column(db.Integer, nullable=False)
    examination_text = db.Column(db.String(200), nullable=False)
    doctor = db.Column(db.Integer, nullable=False)
    doctor_text = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.String(19), nullable=True)
    end_date = db.Column(db.String(19), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    interval = db.Column(db.Integer, nullable=False)
    earliest = db.Column(db.Boolean, nullable=False)
    status = db.Column(db.Boolean, nullable=False)


def check_appointment_request(username, authorization):
    global is_checking
    is_checking = True
    while True:
        with app.app_context():
            appointment_requests = db.session.query(AppointmentRequest).join(User).filter(User.username == username,
                                                                                          AppointmentRequest.status == True)
            for appointment_request in appointment_requests:
                appointments, too_many_requests = bot.get_appointments(city=appointment_request.city,
                                                                       district=appointment_request.district,
                                                                       clinic=appointment_request.clinic,
                                                                       hospital=appointment_request.hospital,
                                                                       examination=appointment_request.examination,
                                                                       doctor=appointment_request.doctor,
                                                                       start_date=appointment_request.start_date,
                                                                       end_date=appointment_request.end_date,
                                                                       authorization=authorization)
                if appointments:
                    if appointment_request.earliest:
                        first_hour = bot.get_appointment_hours(city=appointments[0]["kurum"]["ilIlce"]["mhrsIlId"],
                                                               clinic=appointments[0]["klinik"]["mhrsKlinikId"],
                                                               hospital=appointments[0]["kurum"]["mhrsKurumId"],
                                                               examination=appointments[0]["muayeneYeri"]["id"],
                                                               doctor=appointments[0]["hekim"]["mhrsHekimId"],
                                                               authorization=authorization)[0]
                        print("SLOT:", first_hour[1][0])
                        if bot.make_appointment(slot_id=first_hour[1][0], authorization=authorization):
                            message = f'{appointment_request.clinic_text} kliniği için bir randevu alınmıştır.'
                            play_sound(text=message)
                            if appointment_request.email is not None:
                                send_mail(subject='Randevu Alındı', message=message, receiver=appointment_request.email)
                            db.session.delete(appointment_request)
                    else:
                        message = f'{appointment_request.clinic_text} kliniği için uygun randevu bulundu.'
                        play_sound(text=message)
                        if appointment_request.email is not None:
                            send_mail(subject='Randevu Bulundu', message=message, receiver=appointment_request.email)
                    appointment_request.status = False
                    db.session.commit()
                time.sleep(15)
            if db.session.query(AppointmentRequest).join(User).filter(User.username == username,
                                                                      AppointmentRequest.status == True).count() > 0:
                time.sleep(appointment_requests[0].interval * 60)
            else:  # Eğer randevu talepleri silinirse yani hiç kalmazsa boşuna beklememesi için
                break
    is_checking = False


def play_sound(text):
    tts = gTTS(text=text, lang='tr')
    tts.save("notification.mp3")
    playsound("notification.mp3")
    os.remove("notification.mp3")


def send_mail(subject, message, receiver):
    msg = Message(subject=subject, sender=os.getenv('MAIL_USERNAME'),
                  recipients=[receiver], body=message)
    try:
        mail.send(msg)
        print(f"Mail başarıyla {receiver} adresine gönderildi.")
    except Exception as e:
        print("Mail gönderilemedi! Hata:", e)


@app.before_request
def before_request():
    if request.endpoint not in ['login', 'static'] and 'username' in session:
        try:
            if not bot.check_active(session['authorization']):
                user = User.query.filter_by(username=session['username']).first()
                if user:
                    user.authorization = None
                    db.session.commit()
                session.clear()
                flash("Tekrar Giriş Yapınız!")
                return redirect(url_for("login"))
        except KeyError:
            session.clear()
            flash("Tekrar Giriş Yapınız!")
            return redirect(url_for("login"))


@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for("anasayfa"))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:  # Oturum açıksa
        return redirect(url_for("anasayfa"))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:  # Username ve password girildiyse
            authorization = bot.login(username, password)
            if authorization:  # Username ve password doğruysa
                user = User.query.filter_by(username=username).first()
                if not user:  # İlk defa kullanıcıysa verileri oluştur
                    user = User(username=username, password=password, authorization=authorization)
                    db.session.add(user)
                else:  # Yeniden giriş yapıyorsa verileri güncelle (şifre, auth değişimi olabilir)
                    user.username = username
                    user.password = password
                    user.authorization = authorization
                db.session.commit()
                session['username'] = username
                session['authorization'] = authorization
                # bot.session.headers.update({"Authorization": authorization})
                return redirect(url_for('anasayfa'))
            else:  # Username veya password yanlışsa
                return render_template("login.html", error="Kullanıcı adı veya şifre hatalı!")
    return render_template('login.html')


@app.route('/ana-sayfa')
def anasayfa():
    if 'username' not in session:
        return redirect(url_for('login'))

    global is_checking
    if db.session.query(AppointmentRequest).join(User).filter(User.username == session['username'],
                                                              AppointmentRequest.status == True).count() > 0 and not is_checking:
        threading.Thread(target=check_appointment_request, args=(session['username'], session['authorization']),
                         daemon=True).start()
    personal_data = bot.get_personal_data(session['authorization'])
    return render_template('main-page.html', personal_data=personal_data)


@app.route('/logout')
def logout():
    bot.logout(session['authorization'])
    user = User.query.filter_by(username=session['username']).first()
    if user:
        user.authorization = None
        db.session.commit()
    session.clear()
    return redirect(url_for('login'))


@app.route('/randevu-al', methods=['GET', 'POST'])
def randevu():
    if 'username' not in session:
        return redirect(url_for('login'))

    global is_checking
    districts, clinics, hospitals, examinations, doctors, appointments, hours, selected_city, selected_district, selected_clinic, selected_hospital, selected_examination, selected_doctor, selected_start_date, selected_end_date, searched, interval = [], [], [], [], [], [], [], None, -1, None, -1, -1, -1, None, None, False, None
    cities = bot.get('city', session['authorization'])

    if request.method == 'POST':
        if 'city' in request.form:
            selected_city = request.form.get('city')
            districts = bot.get('district', session['authorization'], selected_city)
            clinics = bot.get('clinic', session['authorization'], selected_city, selected_district)
        if 'district' in request.form:
            selected_district = request.form.get('district')
            clinics = bot.get('clinic', session['authorization'], selected_city, selected_district)
        if 'clinic' in request.form:
            selected_clinic = request.form.get('clinic')
            hospitals = bot.get('hospital', session['authorization'], selected_city, selected_district, selected_clinic)
        if 'hospital' in request.form:
            selected_hospital = request.form.get('hospital')
            examinations = bot.get('examination', session['authorization'], selected_hospital, selected_clinic)
            doctors = bot.get('doctor', session['authorization'], selected_hospital, selected_clinic)
        if 'examination' in request.form:
            selected_examination = request.form.get('examination')
            doctors = bot.get('doctor', session['authorization'], selected_hospital, selected_clinic)
        if 'doctor' in request.form:
            selected_doctor = request.form.get('doctor')
        if 'start_date' in request.form:
            selected_start_date = request.form.get('start_date')
        if 'end_date' in request.form:
            selected_end_date = request.form.get('end_date')
        if 'search' in request.form:
            searched = True
            appointments, too_many_requests = bot.get_appointments(selected_city, selected_district, selected_clinic, selected_hospital,
                                                                   selected_examination, selected_doctor, selected_start_date,
                                                                   selected_end_date, session['authorization'])
            if too_many_requests:
                flash("Çok fazla randevu arama işlemi yaptınız, lütfen bir süre bekleyiniz.")
            else:
                if not appointments and db.session.query(AppointmentRequest).join(User).filter(
                        User.username == session['username']).count() > 0:
                    interval = db.session.query(AppointmentRequest).join(User).filter(
                        User.username == session['username']).first().interval
        if 'appointment' in request.form:
            hours = bot.get_appointment_hours(request.form.get('r-city'), request.form.get('r-clinic'),
                                              request.form.get('r-hospital'), request.form.get('r-examination'),
                                              request.form.get('r-doctor'), session['authorization'])
            if not hours:
                flash("Seçilen randevuya ulaşılamıyor! Yeniden aramayı deneyiniz.")
                return jsonify({'reload': True})
            else:
                return jsonify(hours)
        if 'make_appointment' in request.form:
            selected_hour = request.form.get('hour')
            if bot.make_appointment(selected_hour, session['authorization']):
                flash("Randevu başarıyla alındı. Randevularım sayfasında görüntüleyebilirsiniz.")
            else:
                flash("Randevu alınamadı.")
            return redirect(url_for("randevu"))
        if 'start_check' in request.form:
            user = User.query.filter_by(username=session['username']).first()
            if user:
                appointment_request = AppointmentRequest(
                    user_id=user.id,
                    city=request.form.get('check_city'),
                    city_text=request.form.get('check_city_text'),
                    district=request.form.get('check_district'),
                    district_text=request.form.get('check_district_text'),
                    clinic=request.form.get('check_clinic'),
                    clinic_text=request.form.get('check_clinic_text'),
                    hospital=request.form.get('check_hospital'),
                    hospital_text=request.form.get('check_hospital_text'),
                    examination=request.form.get('check_examination'),
                    examination_text=request.form.get('check_examination_text'),
                    doctor=request.form.get('check_doctor'),
                    doctor_text=request.form.get('check_doctor_text'),
                    start_date=request.form.get('check_start_date') if request.form.get('check_start_date') != "" else None,
                    end_date=request.form.get('check_end_date') if request.form.get('check_end_date') != "" else None,
                    email=request.form.get('email') if request.form.get('email') != "" else None,
                    interval=request.form.get('interval'),
                    earliest=True if "earliest" in request.form else False,
                    status=True)
                db.session.add(appointment_request)
                for req in db.session.query(AppointmentRequest).join(User).filter(User.username == session['username']):
                    req.interval = request.form.get('interval')
                db.session.commit()
                print("Randevu talebi alındı.")
                flash("Randevu talebiniz oluşturuldu.")
                if not is_checking:
                    threading.Thread(target=check_appointment_request,
                                     args=(session['username'], session['authorization']), daemon=True).start()
            else:
                print("Kullanıcı bulunamadı. Yeniden giriş yapınız.")
                flash("Kullanıcı bulunamadı. Yeniden giriş yapınız.")
            return redirect(url_for("randevu"))

    return render_template('randevu-al.html', cities=cities, districts=districts, clinics=clinics, hospitals=hospitals,
                           examinations=examinations, doctors=doctors, selected_city=selected_city,
                           selected_district=selected_district, selected_clinic=selected_clinic,
                           selected_hospital=selected_hospital, selected_examination=selected_examination,
                           selected_doctor=selected_doctor, selected_start_date=selected_start_date,
                           selected_end_date=selected_end_date, appointments=appointments, searched=searched,
                           interval=interval)


@app.route('/randevu-taleplerim', methods=['GET', 'POST'])
def randevu_talepleri():
    if 'username' not in session:
        return redirect(url_for('login'))

    appointment_requests = db.session.query(AppointmentRequest).join(User).filter(User.username == session['username'])
    if request.method == 'POST':
        db.session.delete(AppointmentRequest.query.filter_by(id=request.form.get('req-id')).first())
        db.session.commit()
        print("Randevu talebi silindi.")
        flash("Randevu talebi silindi.")

    return render_template('randevu-taleplerim.html', appointment_requests=appointment_requests)


@app.route('/randevularim', methods=['GET', 'POST'])
def randevularim():
    if 'username' not in session:
        return redirect(url_for('login'))

    message = None
    if request.method == "POST":
        appointment_no = request.form.get("appointment_no")
        if bot.cancel_appointment(appointment_no, session['authorization']):
            message = "Randevunuz başarıyla iptal edildi."
        else:
            message = "Randevu iptali başarısız oldu."

    active_appointments = bot.get_active_appointments(session['authorization'])

    return render_template('randevularim.html', active_appointments=active_appointments, message=message)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


with app.app_context():
    if not os.path.exists(DB_NAME):
        db.create_all()

if __name__ == '__main__':
    app.run()
