import os
import random
import uuid
from functools import wraps
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from PIL import Image as PILImage

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'iprodif-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'iprodif.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)

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

            # Resize if too large
            w, h = img.size
            if w > max_size or h > max_size:
                ratio = min(max_size / w, max_size / h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), PILImage.LANCZOS)

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


# ═══ MODELS ═══

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    city = db.Column(db.String(100))
    bio = db.Column(db.Text, default='')
    avatar_color = db.Column(db.String(7), default='#279FF5')
    is_admin = db.Column(db.Boolean, default=False)
    is_pro = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    annonces = db.relationship('Annonce', backref='author', lazy=True)
    favorites = db.relationship('Favorite', backref='user', lazy=True)

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
        if self.price >= 1000:
            return f"{self.price:,.0f} DH".replace(",", " ")
        return f"{self.price:.0f} DH"

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
    rating = db.Column(db.Integer, nullable=False)  # 1-5
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


@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        return dict(unread_messages=current_user.unread_count)
    return dict(unread_messages=0)


# ═══ ROUTES ═══

@app.route('/')
def index():
    categories = Category.query.all()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Boosted annonces first
    boosted = Annonce.query.filter_by(is_active=True, is_boosted=True)\
        .filter(db.or_(Annonce.boost_until.is_(None), Annonce.boost_until > datetime.utcnow()))\
        .order_by(Annonce.created_at.desc()).limit(5).all()

    sections = []
    for cat in categories:
        annonces = Annonce.query.filter_by(category_id=cat.id, is_active=True)\
            .order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc()).limit(5).all()
        if annonces:
            sections.append({'category': cat, 'annonces': annonces})

    # Recent annonces with pagination
    recent_pagination = Annonce.query.filter_by(is_active=True)\
        .order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    return render_template('index.html', categories=categories, sections=sections,
                           boosted=boosted, recent=recent_pagination)


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
        user = User(username=username, email=email, phone=phone, city=city,
                     avatar_color=random.choice(colors))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Bienvenue sur i-prodif !", "success")
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/connexion', methods=['GET', 'POST'])
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


# ═══ PHASE 4 : PROFIL VENDEUR PUBLIC ═══

@app.route('/vendeur/<int:user_id>')
def seller_profile(user_id):
    seller = User.query.get_or_404(user_id)
    annonces = Annonce.query.filter_by(user_id=seller.id, is_active=True)\
        .order_by(Annonce.created_at.desc()).all()
    reviews = Review.query.filter_by(seller_id=seller.id)\
        .order_by(Review.created_at.desc()).all()

    can_review = False
    if current_user.is_authenticated and current_user.id != seller.id:
        existing = Review.query.filter_by(reviewer_id=current_user.id, seller_id=seller.id).first()
        if not existing:
            can_review = True

    return render_template('vendeur.html', seller=seller, annonces=annonces,
                           reviews=reviews, can_review=can_review)


@app.route('/vendeur/<int:user_id>/avis', methods=['POST'])
@login_required
def add_review(user_id):
    seller = User.query.get_or_404(user_id)
    if current_user.id == seller.id:
        abort(403)

    existing = Review.query.filter_by(reviewer_id=current_user.id, seller_id=seller.id).first()
    if existing:
        flash("Vous avez deja laisse un avis.", "error")
        return redirect(url_for('seller_profile', user_id=user_id))

    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or rating < 1 or rating > 5:
        flash("Note invalide (1-5).", "error")
        return redirect(url_for('seller_profile', user_id=user_id))

    review = Review(reviewer_id=current_user.id, seller_id=seller.id,
                    rating=rating, comment=comment)
    db.session.add(review)
    db.session.commit()
    flash("Avis publie !", "success")
    return redirect(url_for('seller_profile', user_id=user_id))


# ═══ PHASE 4 : BOOST ═══

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


# ═══ PHASE 4 : SIGNALEMENT ═══

@app.route('/annonce/<int:id>/signaler', methods=['POST'])
@login_required
def report_annonce(id):
    annonce = Annonce.query.get_or_404(id)
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash("Veuillez indiquer une raison.", "error")
        return redirect(url_for('annonce_detail', id=id))

    report = Report(reporter_id=current_user.id, annonce_id=id, reason=reason)
    db.session.add(report)
    annonce.is_flagged = True
    annonce.flag_reason = reason
    db.session.commit()
    flash("Signalement envoye. Merci.", "success")
    return redirect(url_for('annonce_detail', id=id))


# ═══ PHASE 4 : ADMIN PANEL ═══

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_annonces = Annonce.query.filter_by(is_active=True).count()
    total_messages = Message.query.count()
    flagged = Annonce.query.filter_by(is_flagged=True, is_active=True).count()
    reports = Report.query.filter_by(is_resolved=False).count()
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_annonces = Annonce.query.order_by(Annonce.created_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                           total_users=total_users, total_annonces=total_annonces,
                           total_messages=total_messages, flagged=flagged,
                           reports_count=reports,
                           recent_users=recent_users, recent_annonces=recent_annonces)


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


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


# ═══ ANNONCES (Phase 2) ═══

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
        delivery = request.form.get('delivery') == 'on'

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

        photo1 = save_photo(request.files.get('photo1'))
        photo2 = save_photo(request.files.get('photo2'))
        photo3 = save_photo(request.files.get('photo3'))

        annonce = Annonce(title=title, description=description, price=price, city=city,
                          state=state, delivery=delivery, photo1=photo1, photo2=photo2,
                          photo3=photo3, user_id=current_user.id, category_id=category_id)
        db.session.add(annonce)
        db.session.commit()
        flash("Annonce publiee !", "success")
        return redirect(url_for('annonce_detail', id=annonce.id))

    return render_template('deposer.html', categories=categories)


@app.route('/annonce/<int:id>')
def annonce_detail(id):
    annonce = Annonce.query.get_or_404(id)
    annonce.views += 1
    db.session.commit()

    is_fav = False
    if current_user.is_authenticated:
        is_fav = current_user.has_favorited(annonce.id)

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
        annonce.delivery = request.form.get('delivery') == 'on'
        try:
            annonce.price = float(request.form.get('price', '0'))
        except ValueError:
            flash("Prix invalide.", "error")
            return render_template('deposer.html', categories=categories, annonce=annonce, edit=True)

        for i, key in enumerate(['photo1', 'photo2', 'photo3'], 1):
            new = save_photo(request.files.get(key))
            if new:
                setattr(annonce, key, new)

        db.session.commit()
        flash("Annonce modifiee !", "success")
        return redirect(url_for('annonce_detail', id=annonce.id))

    return render_template('deposer.html', categories=categories, annonce=annonce, edit=True)


# ═══ FAVORIS (Phase 3) ═══

@app.route('/favori/toggle/<int:annonce_id>', methods=['POST'])
@login_required
def toggle_favorite(annonce_id):
    fav = Favorite.query.filter_by(user_id=current_user.id, annonce_id=annonce_id).first()
    if fav:
        db.session.delete(fav)
        db.session.commit()
        flash("Retire des favoris.", "success")
    else:
        db.session.add(Favorite(user_id=current_user.id, annonce_id=annonce_id))
        db.session.commit()
        flash("Ajoute aux favoris !", "success")
    return redirect(request.referrer or url_for('annonce_detail', id=annonce_id))


@app.route('/favoris')
@login_required
def favorites_page():
    favs = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
    annonces = [f.annonce for f in favs if f.annonce.is_active]
    return render_template('favoris.html', annonces=annonces)


# ═══ MESSAGERIE (Phase 3) ═══

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
        conversations.append({
            'contact': contact, 'last_message': last_msg, 'unread': unread,
            'annonce': related.annonce if related else None
        })
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
    return redirect(url_for('conversation', contact_id=contact_id))


@app.route('/recherche')
def search():
    q = request.args.get('q', '').strip()
    cat_id = request.args.get('cat', type=int)
    city = request.args.get('city', '').strip()
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
    if price_min:
        query = query.filter(Annonce.price >= price_min)
    if price_max:
        query = query.filter(Annonce.price <= price_max)
    if state:
        query = query.filter_by(state=state)

    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = query.order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    categories = Category.query.all()
    return render_template('search.html', annonces=pagination.items, categories=categories,
                           q=q, cat_id=cat_id, city=city, price_min=price_min,
                           price_max=price_max, state=state, pagination=pagination)


@app.route('/categorie/<slug>')
def category_page(slug):
    cat = Category.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = Annonce.query.filter_by(category_id=cat.id, is_active=True)\
        .order_by(Annonce.is_boosted.desc(), Annonce.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    categories = Category.query.all()
    return render_template('search.html', annonces=pagination.items, categories=categories,
                           cat_id=cat.id, q='', city='', price_min=None,
                           price_max=None, state='', current_cat=cat, pagination=pagination)


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

    # Create admin if not exists
    if not User.query.filter_by(is_admin=True).first():
        admin = User(username='admin', email='admin@i-prodif.com',
                     avatar_color='#e63946', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()


with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
