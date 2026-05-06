import os
import random
import uuid
import secrets
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message as MailMessage
from dotenv import load_dotenv

load_dotenv()

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from PIL import Image as PILImage

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'iprodif.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp-relay.brevo.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('i-prodif', 'noreply@i-prodif.com')

SITE_URL = 'https://i-prodif.com'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

PAYS = {
    'MAR': {'nom': 'Maroc', 'devise': 'MAD', 'symbole': 'DH', 'villes': ['Casablanca', 'Rabat', 'Marrakech', 'Fès', 'Tanger', 'Agadir', 'Meknès', 'Oujda', 'Kenitra', 'Tétouan']},
    'DZA': {'nom': 'Algérie', 'devise': 'DZD', 'symbole': 'DA', 'villes': ['Alger', 'Oran', 'Constantine', 'Annaba', 'Blida', 'Batna', 'Djelfa', 'Sétif', 'Sidi Bel Abbès', 'Biskra']},
    'TUN': {'nom': 'Tunisie', 'devise': 'TND', 'symbole': 'DT', 'villes': ['Tunis', 'Sfax', 'Sousse', 'Kairouan', 'Bizerte', 'Gabès', 'Ariana', 'Gafsa', 'Monastir', 'Ben Arous']},
    'SEN': {'nom': 'Sénégal', 'devise': 'XOF', 'symbole': 'CFA', 'villes': ['Dakar', 'Thiès', 'Kaolack', 'Ziguinchor', 'Saint-Louis', 'Diourbel', 'Louga', 'Tambacounda', 'Kolda', 'Fatick']},
    'CIV': {'nom': "Côte d'Ivoire", 'devise': 'XOF', 'symbole': 'CFA', 'villes': ['Abidjan', 'Bouaké', 'Daloa', 'San-Pédro', 'Yamoussoukro', 'Korhogo', 'Man', 'Divo', 'Gagnoa', 'Abengourou']},
    'CMR': {'nom': 'Cameroun', 'devise': 'XAF', 'symbole': 'CFA', 'villes': ['Douala', 'Yaoundé', 'Garoua', 'Bamenda', 'Maroua', 'Bafoussam', 'Ngaoundéré', 'Bertoua', 'Kumba', 'Nkongsamba']},
    'FRA': {'nom': 'France', 'devise': 'EUR', 'symbole': '€', 'villes': ['Paris', 'Lyon', 'Marseille', 'Toulouse', 'Nice', 'Nantes', 'Strasbourg', 'Montpellier', 'Bordeaux', 'Lille']},
    'BEL': {'nom': 'Belgique', 'devise': 'EUR', 'symbole': '€', 'villes': ['Bruxelles', 'Liège', 'Gand', 'Anvers', 'Bruges', 'Namur', 'Mons', 'Charleroi', 'Louvain', 'Hasselt']},
    'CHE': {'nom': 'Suisse', 'devise': 'CHF', 'symbole': 'CHF', 'villes': ['Zurich', 'Genève', 'Bâle', 'Lausanne', 'Berne', 'Winterthour', 'Lucerne', 'Saint-Gall', 'Lugano', 'Bienne']},
}

SOUS_CATEGORIES = {
    'immobilier': ['Ventes', 'Locations', 'Colocations', 'Bureaux & Commerces', 'Terrains'],
    'vehicules': ['Voitures', 'Motos', 'Camions', 'Bateaux', 'Caravaning', 'Utilitaires'],
    'electronique': ['Téléphones', 'Ordinateurs', 'Tablettes', 'TV & Audio', 'Consoles', 'Accessoires'],
    'mode': ['Vêtements Femme', 'Vêtements Homme', 'Chaussures', 'Sacs & Accessoires', 'Montres & Bijoux'],
    'maison-jardin': ['Meubles', 'Électroménager', 'Décoration', 'Bricolage', 'Jardinage'],
    'emploi': ["Offres d'emploi", 'Formations', 'Alternance', 'Freelance'],
    'loisirs': ['Sports & Fitness', 'Jeux vidéo', 'Livres & BD', 'Musique', 'Films & Séries'],
    'famille': ['Puériculture', 'Jouets', 'Vêtements Enfants', 'Mobilier Bébé'],
    'animaux': ['Chiens', 'Chats', 'Oiseaux', 'Accessoires Animaux'],
    'services': ['Cours particuliers', 'Déménagement', 'Réparation', 'Baby-sitting', 'Nettoyage'],
    'vacances': ['Locations vacances', 'Hôtels', 'Circuits', 'Vols'],
}

from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

limiter = Limiter(get_remote_address, app=app, default_limits=[])
mail = Mail(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter.'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(file, max_size=1200):
    if file and file.filename and allowed_file(file.filename):
        try:
            img = PILImage.open(file)
            img = img.convert('RGB')
            w, h = img.size
            if w > max_size or h > max_size:
                ratio = min(max_size / w, max_size / h)
                img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
            filename = f"{uuid.uuid4().hex}.jpg"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            img.save(filepath, 'JPEG', quality=82, optimize=True)
            return filename
        except Exception as e:
            print(f"Erreur photo: {e}")
            return None
    return None


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def send_email(to, subject, body):
    try:
        msg = MailMessage(subject, recipients=[to], html=body)
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erreur email: {e}")
        return False


def slugify(text):
    import re
    text = text.lower().strip()
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')


# ═══ MODELS ═══

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    city = db.Column(db.String(100))
    country = db.Column(db.String(3), default='MAR')
    bio = db.Column(db.Text, default='')
    avatar_color = db.Column(db.String(7), default='#279FF5')
    is_admin = db.Column(db.Boolean, default=False)
    is_pro = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verify_token = db.Column(db.String(100), nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    annonces = db.relationship('Annonce', backref='author', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True,
                                    foreign_keys='Notification.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def initial(self):
        return self.username[0].upper() if self.username else '?'

    @property
    def unread_count(self):
        return Message.query.filter_by(recipient_id=self.id, is_read=False).count()

    @property
    def unread_notifications(self):
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()

    def has_favorited(self, annonce_id):
        return Favorite.query.filter_by(user_id=self.id, annonce_id=annonce_id).first() is not None

    @property
    def avg_rating(self):
        reviews = Review.query.filter_by(seller_id=self.id).all()
        if not reviews:
            return 0
        return round(sum(r.rating for r in reviews) / len(reviews), 1)

    @property
    def review_count(self):
        return Review.query.filter_by(seller_id=self.id).count()

    @property
    def active_annonces_count(self):
        return Annonce.query.filter_by(user_id=self.id, is_active=True).count()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), default='📦')
    slug = db.Column(db.String(100), unique=True, nullable=False)
    annonces = db.relationship('Annonce', backref='category', lazy=True)


class Annonce(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(3), default='MAR')
    currency = db.Column(db.String(3), default='MAD')
    subcategory = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(50), default='Bon etat')
    delivery = db.Column(db.Boolean, default=False)
    photo1 = db.Column(db.String(300))
    photo2 = db.Column(db.String(300))
    photo3 = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_boosted = db.Column(db.Boolean, default=False)
    boost_until = db.Column(db.DateTime, nullable=True)
    is_flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(300))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

    @property
    def slug(self):
        return f"{self.id}-{slugify(self.title)}"

    @property
    def canonical_url(self):
        return f"{SITE_URL}/annonce/{self.slug}"

    @property
    def time_ago(self):
        diff = datetime.utcnow() - self.created_at
        if diff.days > 0:
            return f"il y a {diff.days}j"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"il y a {hours}h"
        minutes = diff.seconds // 60
        return f"il y a {minutes}min"

    @property
    def price_display(self):
        symbole = PAYS.get(self.currency, {}).get('symbole', self.currency) if self.currency else 'DH'
        if self.price >= 1000:
            return f"{self.price:,.0f} {symbole}".replace(",", " ")
        return f"{self.price:.0f} {symbole}"

    @property
    def photos(self):
        return [p for p in [self.photo1, self.photo2, self.photo3] if p]

    @property
    def currently_boosted(self):
        if not self.is_boosted:
            return False
        if self.boost_until and self.boost_until < datetime.utcnow():
            return False
        return True

    @property
    def meta_description(self):
        desc = self.description[:150].replace('\n', ' ').strip()
        return f"{desc}... — {self.price_display} à {self.city}"


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    annonce_id = db.Column(db.Integer, db.ForeignKey('annonce.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_messages')
    annonce = db.relationship('Annonce', backref='messages')


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    annonce_id = db.Column(db.Integer, db.ForeignKey('annonce.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    annonce = db.relationship('Annonce', backref='favorites')
    __table_args__ = (db.UniqueConstraint('user_id', 'annonce_id'),)


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='reviews_given')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='reviews_received')
    __table_args__ = (db.UniqueConstraint('reviewer_id', 'seller_id'),)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    annonce_id = db.Column(db.Integer, db.ForeignKey('annonce.id'), nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_resolved = db.Column(db.Boolean, default=False)
    reporter = db.relationship('User', backref='reports')
    annonce = db.relationship('Annonce', backref='reports')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_notification(user_id, type, message, link=None):
    notif = Notification(user_id=user_id, type=type, message=message, link=link)
    db.session.add(notif)
    db.session.commit()


@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        return dict(
            unread_messages=current_user.unread_count,
            unread_notifications=current_user.unread_notifications,
            pays=PAYS, sous_categories=SOUS_CATEGORIES, site_url=SITE_URL
        )
    return dict(unread_messages=0, unread_notifications=0,
                pays=PAYS, sous_categories=SOUS_CATEGORIES, site_url=SITE_URL)


# ═══ SEO ROUTES ═══

@app.route('/robots.txt')
def robots_txt():
    content = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /profil
Disallow: /messages
Disallow: /favoris
Disallow: /notifications

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap():
    urls = []
    urls.append(f'<url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>')
    categories = Category.query.all()
    for cat in categories:
        urls.append(f'<url><loc>{SITE_URL}/categorie/{cat.slug}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>')
    annonces = Annonce.query.filter_by(is_active=True).order_by(Annonce.created_at.desc()).limit(5000).all()
    for a in annonces:
        lastmod = a.created_at.strftime('%Y-%m-%d')
        urls.append(f'<url><loc>{SITE_URL}/annonce/{a.slug}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>'
    return Response(xml, mimetype='application/xml')


# ═══ ROUTES ═══

@app.route('/')
def index():
    categories = Category.query.all()
    page = request.args.get('page', 1, type=int)
    country_filter = request.args.get('country', '').strip()
    boosted_q = Annonce.query.filter_by(is_active=True, is_boosted=True)\
        .filter(db.or_(Annonce.boost_until.is_(None), Annonce.boost_until > datetime.utcnow()))
    if country_filter:
        boosted_q = boosted_q.filter_by(country=country_filter)
    boosted = boosted_q.order_by(Annonce.created_at.desc()).limit(5).all()
    sections = []
    for cat in categories:
        q = Annonce.query.filter_by(category_id=cat.id, is_active=True)
        if country_filter:
            q = q.filter_by(country=country_filter)
        annonces = q.order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc()).limit(5).all()
        if annonces:
            sections.append({'category': cat, 'annonces': annonces})
    recent_q = Annonce.query.filter_by(is_active=True)
    if country_filter:
        recent_q = recent_q.filter_by(country=country_filter)
    recent_pagination = recent_q.order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('index.html', categories=categories, sections=sections,
                           boosted=boosted, recent=recent_pagination,
                           country_filter=country_filter)


@app.route('/api/villes/<country_code>')
def api_villes(country_code):
    pays = PAYS.get(country_code.upper())
    if not pays:
        return jsonify([])
    return jsonify(pays['villes'])


@app.route('/api/sous-categories/<slug>')
def api_sous_categories(slug):
    return jsonify(SOUS_CATEGORIES.get(slug, []))


@app.route('/notifications')
@login_required
def notifications_page():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/marquer-lues', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/inscription', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        phone = request.form.get('phone', '').strip()
        city = request.form.get('city', '').strip()
        country = request.form.get('country', 'MAR')
        if not username or not email or not password:
            flash("Tous les champs obligatoires doivent etre remplis.", "error")
            return render_template('register.html')
        if password != password2:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template('register.html')
        if len(password) < 6:
            flash("Mot de passe trop court (min 6 caracteres).", "error")
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash("Email deja utilise.", "error")
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur deja pris.", "error")
            return render_template('register.html')
        colors = ['#279FF5', '#4CAF50', '#FF9800', '#9C27B0', '#E91E63', '#00BCD4', '#607D8B', '#FF5722']
        token = secrets.token_urlsafe(32)
        user = User(username=username, email=email, phone=phone, city=city, country=country,
                    avatar_color=random.choice(colors),
                    email_verify_token=token, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        verify_url = url_for('verify_email', token=token, _external=True)
        send_email(email, 'Confirmez votre email — i-prodif',
            f'''<div style="font-family:Arial;max-width:600px;margin:auto">
            <h2 style="color:#279FF5">Bienvenue sur i-prodif !</h2>
            <p>Bonjour {username}, cliquez sur le bouton ci-dessous pour confirmer votre email :</p>
            <a href="{verify_url}" style="background:#279FF5;color:white;padding:12px 24px;
            text-decoration:none;border-radius:6px;display:inline-block;margin:16px 0">
            Confirmer mon email</a>
            <p style="color:#999;font-size:12px">Ce lien expire dans 24h.</p>
            </div>''')
        login_user(user)
        flash("Compte cree ! Verifiez votre email pour activer votre compte.", "success")
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/verifier-email/<token>')
def verify_email(token):
    user = User.query.filter_by(email_verify_token=token).first()
    if not user:
        flash("Lien invalide ou expire.", "error")
        return redirect(url_for('index'))
    user.email_verified = True
    user.email_verify_token = None
    db.session.commit()
    flash("Email confirme ! Votre compte est maintenant actif.", "success")
    return redirect(url_for('index'))


@app.route('/renvoyer-verification')
@login_required
def resend_verification():
    if current_user.email_verified:
        flash("Votre email est deja verifie.", "info")
        return redirect(url_for('profile'))
    token = secrets.token_urlsafe(32)
    current_user.email_verify_token = token
    db.session.commit()
    verify_url = url_for('verify_email', token=token, _external=True)
    send_email(current_user.email, 'Confirmez votre email — i-prodif',
        f'''<div style="font-family:Arial;max-width:600px;margin:auto">
        <h2 style="color:#279FF5">Confirmation email i-prodif</h2>
        <p>Cliquez sur le bouton ci-dessous pour confirmer votre email :</p>
        <a href="{verify_url}" style="background:#279FF5;color:white;padding:12px 24px;
        text-decoration:none;border-radius:6px;display:inline-block;margin:16px 0">
        Confirmer mon email</a>
        <p style="color:#999;font-size:12px">Ce lien expire dans 24h.</p>
        </div>''')
    flash("Email de verification renvoye !", "success")
    return redirect(url_for('profile'))


@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_expires = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()
            reset_url = url_for('reset_password', token=token, _external=True)
            send_email(email, 'Reinitialisation mot de passe — i-prodif',
                f'''<div style="font-family:Arial;max-width:600px;margin:auto">
                <h2 style="color:#279FF5">Reinitialisation de votre mot de passe</h2>
                <p>Cliquez ci-dessous pour choisir un nouveau mot de passe :</p>
                <a href="{reset_url}" style="background:#279FF5;color:white;padding:12px 24px;
                text-decoration:none;border-radius:6px;display:inline-block;margin:16px 0">
                Reinitialiser mon mot de passe</a>
                <p style="color:#999;font-size:12px">Ce lien expire dans 24h.</p>
                </div>''')
        flash("Si cet email existe, un lien de reinitialisation a ete envoye.", "success")
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reinitialiser/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_expires or user.reset_expires < datetime.utcnow():
        flash("Lien invalide ou expire.", "error")
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if len(password) < 6:
            flash("Mot de passe trop court (min 6 caracteres).", "error")
            return render_template('reset_password.html', token=token)
        if password != password2:
            flash("Les mots de passe ne correspondent pas.", "error")
            return render_template('reset_password.html', token=token)
        user.set_password(password)
        user.reset_token = None
        user.reset_expires = None
        db.session.commit()
        flash("Mot de passe modifie ! Vous pouvez vous connecter.", "success")
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)


@app.route('/connexion', methods=['GET', 'POST'])
@limiter.limit("5 per 15 minutes")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.is_banned:
            flash("Ce compte a ete suspendu.", "error")
            return render_template('login.html')
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash("Connexion reussie !", "success")
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash("Email ou mot de passe incorrect.", "error")
    return render_template('login.html')


@app.route('/deconnexion')
@login_required
def logout():
    logout_user()
    flash("Deconnecte.", "success")
    return redirect(url_for('index'))


@app.route('/profil')
@login_required
def profile():
    annonces = Annonce.query.filter_by(user_id=current_user.id).order_by(Annonce.created_at.desc()).all()
    return render_template('profile.html', annonces=annonces)


@app.route('/vendeur/<int:user_id>')
def seller_profile(user_id):
    seller = User.query.get_or_404(user_id)
    annonces = Annonce.query.filter_by(user_id=seller.id, is_active=True)\
        .order_by(Annonce.created_at.desc()).all()
    reviews = Review.query.filter_by(seller_id=seller.id)\
        .order_by(Review.created_at.desc()).all()
    can_review = False
    if current_user.is_authenticated and current_user.id != seller.id:
        if not Review.query.filter_by(reviewer_id=current_user.id, seller_id=seller.id).first():
            can_review = True
    return render_template('vendeur.html', seller=seller, annonces=annonces,
                           reviews=reviews, can_review=can_review)


@app.route('/vendeur/<int:user_id>/avis', methods=['POST'])
@login_required
def add_review(user_id):
    seller = User.query.get_or_404(user_id)
    if current_user.id == seller.id:
        abort(403)
    if Review.query.filter_by(reviewer_id=current_user.id, seller_id=seller.id).first():
        flash("Vous avez deja laisse un avis.", "error")
        return redirect(url_for('seller_profile', user_id=user_id))
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    if not rating or rating < 1 or rating > 5:
        flash("Note invalide (1-5).", "error")
        return redirect(url_for('seller_profile', user_id=user_id))
    db.session.add(Review(reviewer_id=current_user.id, seller_id=seller.id,
                          rating=rating, comment=comment))
    db.session.commit()
    create_notification(seller.id, 'avis',
        f"{current_user.username} vous a laisse un avis {rating}/5",
        url_for('seller_profile', user_id=seller.id))
    flash("Avis publie !", "success")
    return redirect(url_for('seller_profile', user_id=user_id))


@app.route('/annonce/<int:id>/boost', methods=['POST'])
@login_required
def boost_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    if annonce.user_id != current_user.id:
        abort(403)
    annonce.is_boosted = True
    annonce.boost_until = datetime.utcnow() + timedelta(days=7)
    db.session.commit()
    flash("Annonce boostee pour 7 jours !", "success")
    return redirect(url_for('annonce_detail', id=id))


@app.route('/annonce/<int:id>/signaler', methods=['POST'])
@login_required
def report_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash("Veuillez indiquer une raison.", "error")
        return redirect(url_for('annonce_detail', id=id))
    db.session.add(Report(reporter_id=current_user.id, annonce_id=id, reason=reason))
    annonce.is_flagged = True
    annonce.flag_reason = reason
    db.session.commit()
    flash("Signalement envoye. Merci.", "success")
    return redirect(url_for('annonce_detail', id=id))


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html',
                           total_users=User.query.count(),
                           total_annonces=Annonce.query.filter_by(is_active=True).count(),
                           total_messages=Message.query.count(),
                           flagged=Annonce.query.filter_by(is_flagged=True, is_active=True).count(),
                           reports_count=Report.query.filter_by(is_resolved=False).count(),
                           recent_users=User.query.order_by(User.created_at.desc()).limit(10).all(),
                           recent_annonces=Annonce.query.order_by(Annonce.created_at.desc()).limit(10).all())


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    return render_template('admin/users.html', users=User.query.order_by(User.created_at.desc()).all())


@app.route('/admin/user/<int:id>/toggle-ban', methods=['POST'])
@login_required
@admin_required
def admin_toggle_ban(id):
    user = User.query.get_or_404(id)
    if user.is_admin:
        flash("Impossible de bannir un admin.", "error")
        return redirect(url_for('admin_users'))
    user.is_banned = not user.is_banned
    db.session.commit()
    flash(f"{'Banni' if user.is_banned else 'Debanni'} : {user.username}", "success")
    return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:id>/toggle-pro', methods=['POST'])
@login_required
@admin_required
def admin_toggle_pro(id):
    user = User.query.get_or_404(id)
    user.is_pro = not user.is_pro
    db.session.commit()
    flash(f"{'Pro active' if user.is_pro else 'Pro desactive'} : {user.username}", "success")
    return redirect(url_for('admin_users'))


@app.route('/admin/annonces')
@login_required
@admin_required
def admin_annonces():
    filter_type = request.args.get('filter', 'all')
    if filter_type == 'flagged':
        annonces = Annonce.query.filter_by(is_flagged=True, is_active=True).order_by(Annonce.created_at.desc()).all()
    elif filter_type == 'boosted':
        annonces = Annonce.query.filter_by(is_boosted=True, is_active=True).order_by(Annonce.created_at.desc()).all()
    else:
        annonces = Annonce.query.order_by(Annonce.created_at.desc()).limit(50).all()
    return render_template('admin/annonces.html', annonces=annonces, filter_type=filter_type)


@app.route('/admin/annonce/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    annonce.is_active = False
    annonce.is_flagged = False
    db.session.commit()
    flash(f"Annonce #{id} supprimee.", "success")
    return redirect(url_for('admin_annonces'))


@app.route('/admin/annonce/<int:id>/unflag', methods=['POST'])
@login_required
@admin_required
def admin_unflag_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    annonce.is_flagged = False
    annonce.flag_reason = None
    Report.query.filter_by(annonce_id=id, is_resolved=False).update({'is_resolved': True})
    db.session.commit()
    flash(f"Signalement retire pour annonce #{id}.", "success")
    return redirect(url_for('admin_annonces', filter='flagged'))


@app.route('/admin/reports')
@login_required
@admin_required
def admin_reports():
    reports = Report.query.filter_by(is_resolved=False).order_by(Report.created_at.desc()).all()
    return render_template('admin/reports.html', reports=reports)


@app.route('/deposer', methods=['GET', 'POST'])
@login_required
def deposer():
    categories = Category.query.all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', 'Bon etat')
        category_id = request.form.get('category_id', type=int)
        subcategory = request.form.get('subcategory', '').strip()
        delivery = request.form.get('delivery') == 'on'
        country = request.form.get('country', 'MAR')
        currency = PAYS.get(country, {}).get('devise', 'MAD')
        if not title or not description or not price or not city or not category_id:
            flash("Champs obligatoires manquants.", "error")
            return render_template('deposer.html', categories=categories)
        try:
            price = float(price)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("Prix invalide.", "error")
            return render_template('deposer.html', categories=categories)
        annonce = Annonce(title=title, description=description, price=price, city=city,
                          state=state, delivery=delivery, country=country, currency=currency,
                          subcategory=subcategory,
                          photo1=save_photo(request.files.get('photo1')),
                          photo2=save_photo(request.files.get('photo2')),
                          photo3=save_photo(request.files.get('photo3')),
                          user_id=current_user.id, category_id=category_id)
        db.session.add(annonce)
        db.session.commit()
        flash("Annonce publiee !", "success")
        return redirect(url_for('annonce_detail', id=annonce.id))
    return render_template('deposer.html', categories=categories)


@app.route('/annonce/<int:id>')
@app.route('/annonce/<path:slug>')
def annonce_detail(id=None, slug=None):
    if slug and not id:
        try:
            id = int(slug.split('-')[0])
        except (ValueError, IndexError):
            abort(404)
    annonce = Annonce.query.get_or_404(id)
    if not annonce.is_active:
        abort(404)
    db.session.execute(db.text("UPDATE annonce SET views = views + 1 WHERE id = :id"), {"id": id})
    db.session.commit()
    is_fav = current_user.is_authenticated and current_user.has_favorited(annonce.id)
    similaires = Annonce.query.filter(
        Annonce.category_id == annonce.category_id,
        Annonce.id != annonce.id,
        Annonce.is_active == True
    ).order_by(Annonce.created_at.desc()).limit(4).all()
    return render_template('annonce.html', annonce=annonce, similaires=similaires, is_fav=is_fav)


@app.route('/annonce/<int:id>/supprimer', methods=['POST'])
@login_required
def annonce_supprimer(id):
    annonce = Annonce.query.get_or_404(id)
    if annonce.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    annonce.is_active = False
    db.session.commit()
    flash("Annonce supprimee.", "success")
    return redirect(url_for('profile'))


@app.route('/annonce/<int:id>/modifier', methods=['GET', 'POST'])
@login_required
def annonce_modifier(id):
    annonce = Annonce.query.get_or_404(id)
    if annonce.user_id != current_user.id:
        abort(403)
    categories = Category.query.all()
    if request.method == 'POST':
        annonce.title = request.form.get('title', '').strip()
        annonce.description = request.form.get('description', '').strip()
        annonce.city = request.form.get('city', '').strip()
        annonce.state = request.form.get('state', 'Bon etat')
        annonce.category_id = request.form.get('category_id', type=int)
        annonce.subcategory = request.form.get('subcategory', '').strip()
        annonce.delivery = request.form.get('delivery') == 'on'
        annonce.country = request.form.get('country', 'MAR')
        annonce.currency = PAYS.get(annonce.country, {}).get('devise', 'MAD')
        try:
            annonce.price = float(request.form.get('price', '0'))
        except ValueError:
            flash("Prix invalide.", "error")
            return render_template('deposer.html', categories=categories, annonce=annonce, edit=True)
        for key in ['photo1', 'photo2', 'photo3']:
            new = save_photo(request.files.get(key))
            if new:
                setattr(annonce, key, new)
        db.session.commit()
        flash("Annonce modifiee !", "success")
        return redirect(url_for('annonce_detail', id=annonce.id))
    return render_template('deposer.html', categories=categories, annonce=annonce, edit=True)


@app.route('/favori/toggle/<int:annonce_id>', methods=['POST'])
@login_required
def toggle_favorite(annonce_id):
    fav = Favorite.query.filter_by(user_id=current_user.id, annonce_id=annonce_id).first()
    if fav:
        db.session.delete(fav)
        flash("Retire des favoris.", "success")
    else:
        db.session.add(Favorite(user_id=current_user.id, annonce_id=annonce_id))
        flash("Ajoute aux favoris !", "success")
    db.session.commit()
    return redirect(request.referrer or url_for('annonce_detail', id=annonce_id))


@app.route('/favoris')
@login_required
def favorites_page():
    favs = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
    return render_template('favoris.html', annonces=[f.annonce for f in favs if f.annonce.is_active])


@app.route('/messages')
@login_required
def messages_page():
    sent = db.session.query(Message.recipient_id).filter_by(sender_id=current_user.id).distinct()
    received = db.session.query(Message.sender_id).filter_by(recipient_id=current_user.id).distinct()
    contact_ids = set(r[0] for r in sent) | set(r[0] for r in received)
    conversations = []
    for cid in contact_ids:
        contact = User.query.get(cid)
        if not contact:
            continue
        last_msg = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.recipient_id == cid),
                db.and_(Message.sender_id == cid, Message.recipient_id == current_user.id)
            )
        ).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(sender_id=cid, recipient_id=current_user.id, is_read=False).count()
        related = Message.query.filter(
            db.or_(
                db.and_(Message.sender_id == current_user.id, Message.recipient_id == cid),
                db.and_(Message.sender_id == cid, Message.recipient_id == current_user.id)
            ), Message.annonce_id.isnot(None)
        ).order_by(Message.created_at.asc()).first()
        conversations.append({'contact': contact, 'last_message': last_msg, 'unread': unread,
                               'annonce': related.annonce if related else None})
    conversations.sort(key=lambda c: c['last_message'].created_at if c['last_message'] else datetime.min, reverse=True)
    return render_template('messages.html', conversations=conversations)


@app.route('/messages/<int:contact_id>')
@login_required
def conversation(contact_id):
    contact = User.query.get_or_404(contact_id)
    annonce_id = request.args.get('annonce_id', type=int)
    msgs = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == current_user.id, Message.recipient_id == contact_id),
            db.and_(Message.sender_id == contact_id, Message.recipient_id == current_user.id)
        )
    ).order_by(Message.created_at.asc()).all()
    Message.query.filter_by(sender_id=contact_id, recipient_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    annonce = None
    if annonce_id:
        annonce = Annonce.query.get(annonce_id)
    elif msgs:
        for m in msgs:
            if m.annonce_id:
                annonce = m.annonce
                break
    return render_template('conversation.html', contact=contact, messages=msgs, annonce=annonce)


@app.route('/messages/<int:contact_id>/envoyer', methods=['POST'])
@login_required
def send_message(contact_id):
    content = request.form.get('content', '').strip()
    annonce_id = request.form.get('annonce_id', type=int)
    if not content:
        flash("Message vide.", "error")
        return redirect(url_for('conversation', contact_id=contact_id))
    db.session.add(Message(sender_id=current_user.id, recipient_id=contact_id,
                           content=content, annonce_id=annonce_id))
    db.session.commit()
    annonce = Annonce.query.get(annonce_id) if annonce_id else None
    notif_msg = f"Nouveau message de {current_user.username}"
    if annonce:
        notif_msg += f" pour : {annonce.title}"
    create_notification(contact_id, 'message', notif_msg,
                        url_for('conversation', contact_id=current_user.id))
    return redirect(url_for('conversation', contact_id=contact_id))


@app.route('/recherche')
def search():
    q = request.args.get('q', '').strip()
    cat_id = request.args.get('cat', type=int)
    city = request.args.get('city', '').strip()
    country = request.args.get('country', '').strip()
    subcategory = request.args.get('subcategory', '').strip()
    price_min = request.args.get('price_min', type=float)
    price_max = request.args.get('price_max', type=float)
    state = request.args.get('state', '').strip()
    query = Annonce.query.filter_by(is_active=True)
    if q:
        query = query.filter(Annonce.title.ilike(f'%{q}%'))
    if cat_id:
        query = query.filter_by(category_id=cat_id)
    if city:
        query = query.filter(Annonce.city.ilike(f'%{city}%'))
    if country:
        query = query.filter_by(country=country)
    if subcategory:
        query = query.filter_by(subcategory=subcategory)
    if price_min:
        query = query.filter(Annonce.price >= price_min)
    if price_max:
        query = query.filter(Annonce.price <= price_max)
    if state:
        query = query.filter_by(state=state)
    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('search.html', annonces=pagination.items, categories=Category.query.all(),
                           q=q, cat_id=cat_id, city=city, country=country, subcategory=subcategory,
                           price_min=price_min, price_max=price_max, state=state, pagination=pagination)


@app.route('/categorie/<slug>')
def category_page(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    country = request.args.get('country', '').strip()
    subcategory = request.args.get('subcategory', '').strip()
    q = Annonce.query.filter_by(category_id=cat.id, is_active=True)
    if country:
        q = q.filter_by(country=country)
    if subcategory:
        q = q.filter_by(subcategory=subcategory)
    pagination = q.order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=20, error_out=False)
    return render_template('search.html', annonces=pagination.items, categories=Category.query.all(),
                           cat_id=cat.id, q='', city='', country=country, subcategory=subcategory,
                           price_min=None, price_max=None, state='', current_cat=cat, pagination=pagination)


# ═══ INIT DB ═══

def init_db():
    db.create_all()
    if not Category.query.first():
        cats = [
            ('Immobilier', '🏠', 'immobilier'), ('Vehicules', '🚗', 'vehicules'),
            ('Vacances', '✈️', 'vacances'), ('Emploi', '💼', 'emploi'),
            ('Mode', '👗', 'mode'), ('Maison & Jardin', '🏡', 'maison-jardin'),
            ('Famille', '👶', 'famille'), ('Electronique', '📱', 'electronique'),
            ('Loisirs', '🎮', 'loisirs'), ('Animaux', '🐾', 'animaux'),
            ('Services', '🛠', 'services'),
        ]
        for name, icon, slug in cats:
            db.session.add(Category(name=name, icon=icon, slug=slug))
        db.session.commit()
    if not User.query.filter_by(is_admin=True).first():
        admin = User(username='admin', email='admin@i-prodif.com',
                     avatar_color='#e63946', is_admin=True, email_verified=True)
        admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
        db.session.add(admin)
        db.session.commit()


with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)