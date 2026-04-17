import os  # ספרייה לניהול מערכת ההפעלה (נתיבי קבצים, תיקיות)
import uuid  # יצירת מזהים ייחודיים גלובליים (כדי ששמות תמונות לא יחזרו על עצמם)
import json  # עבודה עם פורמט JSON (המרה של רשימות למחרוזות ולהפך)
from flask import Flask, request, jsonify, send_from_directory  # ליבת השרת: ניהול בקשות, תשובות ושליחת קבצים
from flask_cors import CORS  # מאפשר לאתר (Angular) לגשת לשרת למרות שהם בדומיינים/פורטים שונים
from flask_bcrypt import Bcrypt  # ספרייה להצפנה ואימות סיסמאות בצורה מאובטחת
from models import db, User, Recipe, IngredientEntry  # ייבוא המודלים שהגדרנו ב-SQLAlchemy
import jwt  # שימוש ב-JSON Web Tokens לאימות משתמשים ללא שמירת Session בשרת
from functools import wraps  # כלי ליצירת דקורטורים ששומרים על המידע של הפונקציה המקורית
from datetime import datetime, timedelta, timezone  # ניהול זמנים (תוקף לטוקן, תאריכי בקשות)
from PIL import Image, ImageFilter  # ספריית Pillow לעיבוד ועריכת תמונות
from dotenv import load_dotenv

#קובץ זה מכיל משתנים סודיים כמו מפתחות API וסיסמאות שאסור לשתף בקוד הפומבי
load_dotenv() # טעינת המשתנים מקובץ ה-.env


# region אתחול והגדרות בסיס
#Flask היא ספריית פייתון שמאפשרת להפוך קוד פייתון רגיל לשרת אינטרנט (Web Server).
app = Flask(__name__)  # יצירת מופע של אפליקציית הפלאסק

# הגדרת נתיבים למסד הנתונים ויצירת המסד
INSTANCE_FOLDER = os.path.join(app.root_path, 'instance')  # יצירת נתיב לתיקיית הנתונים
DB_FILE = 'recipes.db'  # שם קובץ מסד הנתונים
DB_PATH = os.path.join(INSTANCE_FOLDER, DB_FILE)  # הנתיב המלא לקובץ ה-DB

# הגדרות תצורה (Configuration)
#כמו לוח בקרה שבו את קובעת איך המערכת תתנהג.
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'  # חיבור ה-ORM לקובץ ה-SQLite למסד נתונים
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # כיבוי מערכת התראות לחיסכון במשאבים
# זו מחרוזת טקסט שמשמשת כ"מפתח" להצפנה. רק מי שיש לו את המפתח יכול לחתום על ה-JWT (טוקן הכניסה)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')  # מפתח סודי לחתימה על טוקנים (קריטי לאבטחה!)
# בדיקה קריטית: אם המפתח לא קיים, השרת לא יעלה
if not app.config['SECRET_KEY']:
    raise ValueError("No SECRET_KEY set for Flask application!")

# השורה הזו מחברת פיזית את אובייקט בסיס הנתונים לאפליקציה שרצה כרגע.
db.init_app(app)  # חיבור אובייקט ה-SQLAlchemy לאפליקציה
# דפדפנים הם מאוד חשדניים. הם לא מרשים לאתר שרץ בכתובת אחת (Angular בפורט 4200) לדבר עם שרת בכתובת אחרת (Python בפורט 5000).
CORS(app)  # הפעלת הגנת ה-CORS
# אם מישהו היה פורץ למסד הנתונים שלך, הוא היה רואה רשימה של כל המיילים והסיסמאות של המשתמשים שלך ויכול לגנוב להם את הזהות. עם Bcrypt, גם אם ההאקר פורץ פנימה, הוא רואה רק ג'יבריש חסר תועלת
bcrypt = Bcrypt(app)  # אתחול מערכת ההצפנה

# יצירת תיקיית העלאות במידה ואינה קיימת
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
#כאן יאוחסנו כל התמונות שהמשתמשים מעלים למתכונים שלהם.
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
#כאן יאוחסנו קבצי מסד הנתונים אם הם לא קיימים
if not os.path.exists(INSTANCE_FOLDER):
    os.makedirs(INSTANCE_FOLDER)


# endregion

# --- 2. פונקציות עזר לבדיקת הרשאות (Decorators) ---
# דקורטור הוא "עטיפה" ששמים מעל פונקציה כדי להוסיף לה תפקיד (כמו בדיקת אבטחה) בלי לשנות את הקוד של הפונקציה עצמה. מסמנים אותו בסימן @ מעל הפונקציה.

# פונקציית הגנה שמחזיקה ביד את הפונקציה f ומחליטה מתי להפעיל אותה
def token_required(f):
    @wraps(f)  # הוא דואג שהפונקציה המקורית לא "תשכח" את השם שלה אחרי שעטפנו אותה
    def decorated(*args, **kwargs):  # מאפשרת למעטפת לקבל כל סוג של מידע שנשלח מהמשתמש ולהעביר אותו הלאה בבטחה
        token = None
        # חיפוש כותרת האימות בתוך הבקשה שנשלחה מהדפדפן (Angular)
        if 'Authorization' in request.headers:
            # הטוקן מגיע בפורמט "Bearer <קוד>". split מפריד ביניהם ולוקח רק את הקוד
            token = request.headers['Authorization'].split(" ")[1]

        # אם המשתמש לא שלח שום טוקן, מחזירים שגיאת "חוסר הזדהות" (401)
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            # ניסיון לפענח את הטוקן בעזרת המפתח הסודי שהגדרנו בקובץ ה-.env (SECRET_KEY)
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            # שליפת המשתמש ממסד הנתונים לפי ה-ID שנשמר בתוך הטוקן בזמן הלוגין
            current_user = User.query.filter_by(id=data['user_id']).first()
            # אם הטוקן תקין אבל המשתמש כבר לא קיים במסד הנתונים
            if not current_user:
                return jsonify({'message': 'User no longer exists'}), 401
        except:
            # אם הטוקן פג תוקף, שונה על ידי האקר או לא תקין מבחינה מבנית
            return jsonify({'message': 'Token is invalid or expired!'}), 401

        # אם הכל עבר בהצלחה, מפעילים את הפונקציה המקורית ושולחים לה את המשתמש שמצאנו
        return f(current_user, *args, **kwargs)

    return decorated


# region בדיקת הרשאה של המשתמש
# נראה לי שבעיקרון אני לא חייבת את הדקורטור הזה כי אין לי אפשרות בכלל למחוק או להוסיף מתכון למי שלא מורשה(באנגולר)- לבדוק
# תשובות:
# המשתמש ה"חכם" (האקר): דמייני משתמש שקצת מבין בקוד. הוא לא צריך את הכפתור שלך באנגולר. הוא יכול לפתוח כלי שנקרא Postman (או אפילו דרך ה-Inspect של הדפדפן)
# עקיפת ה-UI (ממשק המשתמש): האנגולר הוא רק "ציור" יפה מעל השרת. כל מה שקורה באנגולר נמצא בשליטת המשתמש (הוא יכול לשנות את הקוד אצלו בדפדפן). השרת (Python) הוא המקום היחיד שנמצא בשליטה מלאה שלך. לכן, השרת חייב להיות "חשדן" ולבדוק כל בקשה שמגיעה אליו, כאילו היא הגיעה מהאקר.

# דקורטור לבדיקת הרשאות לפי תפקיד (למשל: רק אדמין יכול למחוק)
# roles* מאפשר להעביר מספר תפקידים, למשל: ('admin', 'editor')
def roles_required(*roles):
    # פונקציה פנימית שמקבלת את הפונקציה עליה נפעיל את ההגנה
    def decorator(f):
        # שומר על הזהות המקורית של הפונקציה (שם, מיקום בקוד)
        @wraps(f)
        # המעטפת שרצה בפועל; מקבלת את current_user מהדקורטור של הטוקן
        def decorated_function(current_user, *args, **kwargs):
            # בדיקה: האם התפקיד של המשתמש (ששמור ב-DB) נמצא ברשימה המורשת?
            if current_user.role not in roles:
                # 403 Forbidden - המשתמש מזוהה אך אין לו הרשאה לביצוע הפעולה
                return jsonify({'message': 'Permission denied! Low clearance level.'}), 403

            # אם הבדיקה עברה, מריצים את הפונקציה המקורית עם כל הפרמטרים שלה
            return f(current_user, *args, **kwargs)

        # מחזירים את המעטפת המוכנה
        return decorated_function

    # מחזירים את הדקורטור המלא
    return decorator


# endregion


# --- 3. Routes בסיסיים (Endpoints) ---

@app.route('/')
def home():
    return "Recipe Sharing Platform Server is running!", 200


# region כניסה
@app.route('/login', methods=['POST'])  # נתיב התחברות והנפקת טוקן (JWT)
def login():
    # קבלת הפרטים מהמשתמש
    data = request.get_json()# שליפת הנתונים שנשלחו מה-Angular (בפורמט JSON)
    email = data.get('email')# חילוץ המייל מתוך הנתונים
    password = data.get('password')# חילוץ הסיסמה מתוך הנתונים

    # לוודא שלא נשלחו שדות ריקים
    if not email or not password:
        return jsonify({'message': 'Missing email or password'}), 400

    # חיפוש המשתמש בבסיס הנתונים לפי המייל
    user = User.query.filter_by(email=email).first()

    # בדיקה כפולה: האם המשתמש קיים והאם הסיסמה נכונה
    # bcrypt.check_password_hash משווה בין הסיסמה הגלויה לגיבוב השמור
    if not user or not bcrypt.check_password_hash(user.password, password):
        # 401 Unauthorized - פרטי הזיהוי שגויים
        return jsonify({'message': 'Invalid credentials'}), 401

    # יצירת המטען (Payload) של הטוקן - המידע שיעבור עם המשתמש לכל מקום
    token_payload = {
        'user_id': user.id,  # זיהוי ייחודי
        'role': user.role,  # תפקיד (לצורך הרשאות)
        # קביעת תוקף לטוקן - כאן ל-24 שעות מרגע הכניסה
        'exp': datetime.utcnow() + timedelta(hours=24)
    }

    # יצירת הטוקן וחתימתו עם ה-SECRET_KEY של האפליקציה
    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm="HS256")

    # החזרת תשובה חיובית לאנגולר עם הטוקן ופרטי המשתמש הבסיסיים
    return jsonify({
        'message': 'Login successful',# הודעת הצלחה
        'token': token,# הטוקן שנוצר
        'user': {
            'id': user.id,# מזהה המשתמש
            'email': user.email,# המייל של המשתמש
            'role': user.role,# תפקיד המשתמש
            'is_approved_uploader': user.is_approved_uploader# האם המשתמש מורשה להעלות מתכונים
        }
    }), 200  # 200 OK - הפעולה הצליחה


# endregion

# region הרשמת משתמש חדש
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()  # שליפת הנתונים שנשלחו מה-Angular (בפורמט JSON)
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({'message': 'Missing email or password'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'User with this email already exists'}), 409
    # הצפנת הסיסמה (Hashing) לפני השמירה - אבטחה בסיסית חובה
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    # יצירת אובייקט משתמש חדש עם הנתונים שהתקבלו
    new_user = User(
        email=email,
        password=hashed_password,
        role='Reader',
        is_approved_uploader=False
    )
    try:
        # שמירת המשתמש החדש לתוך קובץ ה-recipes.db
        new_user.save()
        # קוד 201 מציין שהפעולה הצליחה ונוצר משאב חדש במערכת
        return jsonify({'message': 'User registered successfully!'}), 201
    except Exception as e:
        # במקרה של תקלה לא צפויה (למשל בעיה בכתיבה לקובץ)
        return jsonify({'message': f'Error saving user: {str(e)}'}), 500


# endregion


# region פונקציה לעיבוד ושמירת תמונה בכמה וריאציות
def process_and_save_image(image_file):
    # יצירת שם ייחודי (UUID) כדי למנוע דריסת קבצים בעלי שם זהה
    unique_filename = str(uuid.uuid4())
    # חילוץ הסיומת (למשל .jpg) והפיכתה לאותיות קטנות למניעת בעיות
    extension = os.path.splitext(image_file.filename)[1].lower()
    # הגדרת הנתיב המלא לשמירת התמונה המקורית
    original_path = os.path.join(UPLOAD_FOLDER, f'{unique_filename}_original{extension}')
    # רשימה שתכיל את כל הנתיבים של הגרסאות המעובדות
    variation_paths = []

    try:
        # פתיחת התמונה בעזרת ספריית Pillow
        img = Image.open(image_file)
        # שמירת המקור בתיקיית העלאות
        img.save(original_path)

        # הגדרת מילון של שינויים (וריאציות) לביצוע על התמונה
        variations = {
            'bw': lambda i: i.convert('L'),  # המרה לשחור-לבן
            'rotate_90': lambda i: i.rotate(90, expand=True),  # סיבוב ב-90 מעלות ומבטיח שהשוליים לא יחתכו
            'sharpen': lambda i: i.filter(ImageFilter.SHARPEN)  # חידוד התמונה
        }

        # מעבר בלולאה על כל שינוי שהגדרנו
        for name, func in variations.items():
            # ביצוע השינוי על עותק של התמונה המקורית
            img_processed = func(img.copy())
            # יצירת נתיב ייחודי לגרסה המעובדת (למשל: id_bw.jpg)
            variation_path = os.path.join(UPLOAD_FOLDER, f'{unique_filename}_{name}{extension}')
            # שמירת הקובץ המעובד על הדיסק
            img_processed.save(variation_path)
            # הוספת הנתיב לרשימת התוצאות
            variation_paths.append(variation_path)

        # החזרת הנתיב המקורי ורשימת כל הגרסאות הנוספות שיצרנו
        return original_path, variation_paths
    except Exception as e:
        # במקרה של שגיאה (למשל קובץ פגום שאינו תמונה), נדפיס אותה ונחזיר רשימה ריקה
        print(f"Error processing image: {e}")
        return None, []


# endregion

# נתיב להוספת מתכון חדש - דורש טוקן והרשאות מתאימות
@app.route('/recipes', methods=['POST'])
@token_required
@roles_required('Admin', 'Uploader')  # רק אדמין או מעלה מורשה יכולים להוסיף
def add_recipe(current_user):
    # בדיקה שצירפו תמונה - בלי תמונה אי אפשר ליצור מתכון
    if 'image' not in request.files:
        return jsonify({'message': 'Image file is required'}), 400
    image_file = request.files['image']

    try:
        # שליפת נתוני המתכון (שנשלחו כטקסט JSON בתוך FormData)
        recipe_data_str = request.form.get('data') or request.form.get('recipe')
        if not recipe_data_str:
            return jsonify({'message': 'Recipe data is missing'}), 400
        # המרת הטקסט למילון פייתון (Dictionary)
        data = json.loads(recipe_data_str)
    except json.JSONDecodeError:
        return jsonify({'message': 'Invalid JSON format'}), 400

    # הפעלת פונקציית העיבוד לשמירת התמונה המקורית והגרסאות שלה (Pillow)
    original_path, variation_paths = process_and_save_image(image_file)
    if not original_path:
        return jsonify({'message': 'Image processing failed'}), 500

    try:
        # 1. יצירת אובייקט המתכון ושמירתו בטבלת Recipes
        new_recipe = Recipe(
            title=data['title'],
            description=data['description'],
            image_path=original_path,
            type=data['type'],
            prep_time=data.get('prep_time', 0),
            user_id=current_user.id  # קישור למשתמש שיוצר את המתכון
        )
        # שמירת נתיבי התמונות המעובדות בשדה המיוחד שלהן
        new_recipe.set_variations(variation_paths)
        new_recipe.save()  # שמירה ראשונית כדי לקבל ID למתכון

        # 2. יצירת רשימת המצרכים וקישורם למתכון החדש
        ingredient_objects = []
        for ing in data['ingredients']:
            new_ingredient = IngredientEntry(
                product=ing['product'],
                amount=ing['amount'],
                unit=ing['unit'],
                recipe_id=new_recipe.id  # קישור למתכון שיצרנו שורה מעל
            )
            ingredient_objects.append(new_ingredient)
        # ה-Session הוא מרחב עבודה זמני. את אומרת לשרת: "אני רוצה להוסיף מתכון, ואז להוסיף 5 מצרכים". השרת שומר את הכל ב"עגלה" (בזיכרון). רק בסוף, כשאת כותבת db.session.commit(), הוא כותב הכל בבת אחת לקובץ ה-recipes.db.
        # כמו הדוגמא שהוא הביא לי עם העגלה והסופרמרקט הקומיט הוא הקופה
        # הוספת כל המצרכים למסד הנתונים בבת אחת
        db.session.add_all(ingredient_objects)
        # אישור סופי של כל השינויים (מתכון + מצרכים)
        db.session.commit()

        return jsonify({'message': 'Recipe added successfully', 'id': new_recipe.id}), 201
    except Exception as e:
        # אם משהו נכשל, מבצעים "Rollback" - ביטול כל מה שנכתב ב-Session הנוכחי
        db.session.rollback()
        return jsonify({'message': f'Internal error: {e}'}), 500


# נתיב המאפשר לדפדפן (Angular) להציג את התמונות השמורות בשרת
# methods=['GET'] - כי אנחנו רק מבקשים לקבל מידע, לא לשלוח או לשנות
@app.route('/uploads/<filename>', methods=['GET'])
def get_uploaded_file(filename):
    # הפונקציה מקבלת את שם הקובץ דרך ה-URL (למשל: abc-123.jpg)

    # send_from_directory היא פונקציה מאובטחת של Flask
    # היא ניגשת לתיקייה שהגדרנו (UPLOAD_FOLDER) ושולחת את הקובץ הפיזי למשתמש
    return send_from_directory(UPLOAD_FOLDER, filename)


# נתיב לקבלת כל המתכונים הקיימים במערכת
@app.route('/recipes', methods=['GET'])
def get_all_recipes():
    try:
        # שליפת כל הרשומות מטבלת המתכונים במסד הנתונים
        recipes = Recipe.query.all()
        recipes_list = []

        # מעבר על כל מתכון שהתקבל מה-DB
        for recipe in recipes:
            # שליפת רשימת הנתיבים של התמונות (מקור + מעובדות)
            paths = recipe.get_variations()

            # בניית מילון נתונים עבור כל מתכון בפורמט JSON
            recipes_list.append({
                'id': recipe.id,
                'title': recipe.title,
                'description': recipe.description,
                'type': recipe.type,
                'prep_time': recipe.prep_time,
                'author_email': recipe.author.email,  # שליפה מהטבלה המקושרת (Users)
                'ingredients_count': len(recipe.ingredients),  # ספירת מספר המצרכים במתכון
                # בחירת תמונה להצגה: אם קיימת וריאציה (מעובדת), נשלח אותה. אם לא, נשלח ריק.
                # os.path.basename מחלץ רק את שם הקובץ מתוך הנתיב המלא
                # 1. את בודקת אם יש יותר מתמונה אחת (len(paths) > 1).
                # 2. אם כן, את לוקחת את התמונה שנמצאת במיקום השני (paths[1]). בדרך כלל זו תהיה אחת התמונות המעובדות.
                # 3. os.path.basename לוקח רק את שם הקובץ (למשל image_123.jpg) בלי כל התיקיות שבדרך
                # בסוף לא השתמשתי בזה
                # 'image_url': f'/uploads/{os.path.basename(paths[1]) if len(paths) > 1 else ""}'
                ## אנחנו מוודאים שיש לפחות נתיב אחד (המקורי) ואז שולחים אותו.
                # אם אין כלום, נשלח מחרוזת ריקה כדי שהאנגולר יפעיל את ה-placeholder
                'image_url': f'/uploads/{os.path.basename(paths[0]) if len(paths) > 0 else ""}'
            })

        # החזרת הרשימה המלאה לאנגולר כפורמט JSON
        return jsonify(recipes_list)
    except Exception as e:
        # במקרה של תקלה בשרת (למשל בעיה בחיבור ל-DB)
        return jsonify({'message': f'Server error: {e}'}), 500


# נתיב לקבלת פרטים מלאים על מתכון אחד ספציפי לפי ה-ID שלו
@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def get_single_recipe(recipe_id):
    # שליפת המתכון מה-DB או החזרת שגיאה 404 אם הוא לא קיים
    recipe = Recipe.query.get_or_404(recipe_id)

    # המרת אובייקטי המצרכים לרשימה פשוטה של מילונים (JSON)
    ingredients_list = [
        {'product': i.product, 'amount': i.amount, 'unit': i.unit}
        for i in recipe.ingredients
    ]

    # קבלת רשימת הנתיבים של כל התמונות השמורות למתכון זה
    variation_paths_list = recipe.get_variations()

    # החזרת אובייקט JSON מלא הכולל את פרטי המתכון, הכותב והתמונות
    return jsonify({
        'id': recipe.id,
        'title': recipe.title,
        'description': recipe.description,
        'type': recipe.type,
        'prep_time': recipe.prep_time,
        'author_email': recipe.author.email,  # שליפה מהטבלה המקושרת (Users)
        'ingredients': ingredients_list,
        # יצירת הכתובת לתמונה המקורית עבור האנגולר
        'image_original_url': f'/uploads/{os.path.basename(recipe.image_path)}',
        # יצירת רשימה של כתובות לכל הווריאציות המעובדות
        'image_variations': [f'/uploads/{os.path.basename(p)}' for p in variation_paths_list]
    }), 200


# נתיב למחיקת מתכון - מותר רק למנהל (Admin)
@app.route('/recipes/<int:recipe_id>', methods=['DELETE'])
@token_required
@roles_required('Admin')
def delete_recipe(current_user, recipe_id):
    # חיפוש המתכון לפי ID; אם לא נמצא, מחזיר 404 באופן אוטומטי
    recipe_to_delete = Recipe.query.get_or_404(recipe_id)

    try:
        # א. מחיקת קובץ התמונה המקורית מהשרת
        if os.path.exists(recipe_to_delete.image_path):
            os.remove(recipe_to_delete.image_path)

        # ב. מחיקת כל גרסאות התמונות המעובדות (ווריאציות)
        for path in recipe_to_delete.get_variations():
            if os.path.exists(path):
                os.remove(path)

        # ג. מחיקת הרשומה של המתכון ממסד הנתונים
        db.session.delete(recipe_to_delete)
        # ד. שמירת השינויים באופן סופי
        db.session.commit()

        return jsonify({'message': 'Recipe deleted successfully'}), 200
    except Exception as e:
        # במידה וחלה שגיאה, מבטלים את הפעולות במסד הנתונים
        db.session.rollback()
        print(f"Delete error: {e}")
        return jsonify({'message': 'Internal server error'}), 500


# --- מסלולי ניהול משתמשים (Admin) ---
@app.route('/admin/requests', methods=['GET'])
@token_required
@roles_required('Admin')
def get_pending_users(current_user):
    """שליפת משתמשים שביקשו הרשאה (request_date אינו ריק)"""
    try:
        # סינון: רק משתמשי Reader שבאמת לחצו על הכפתור (request_date != None)
        pending_users = User.query.filter(
            User.role == 'Reader',
            User.request_date != None
        ).all()

        pending_list = []
        for user in pending_users:
            # הכנת המידע למשלוח לאנגולר
            pending_list.append({
                'id': user.id,
                'email': user.email,
                # המרת התאריך לפורמט טקסט תקני (ISO)
                'created_at': user.request_date.isoformat() if user.request_date else ""
            })

        # החזרת הרשימה לממשק הניהול באנגולר
        return jsonify(pending_list), 200
    except Exception as e:
        # טיפול בשגיאות במידה ויש תקלה במסד הנתונים
        return jsonify({'message': str(e)}), 500


# נתיב המאפשר למשתמש מחובר לבקש אישור להעלות מתכונים
@app.route('/request-upload-permission', methods=['POST'])
@token_required  # חובה לשלוח טוקן כדי שנדע מי המשתמש
def request_upload_permission(current_user):
    """עדכון תאריך הבקשה של המשתמש כדי שיופיע אצל המנהל"""
    try:
        # עדכון שדה תאריך הבקשה לזמן הנוכחי
        # datetime.utcnow() מבטיח זמן אחיד לכל המשתמשים ללא קשר לאזור זמן
        current_user.request_date = datetime.utcnow()

        # שמירת השינוי במסד הנתונים
        current_user.save()

        # החזרת הודעת אישור לאנגולר
        return jsonify({'message': 'בקשתך נשלחה למנהל'}), 200
    except Exception as e:
        # במקרה של תקלה (למשל בעיה בחיבור ל-DB)
        return jsonify({'message': str(e)}), 500


# הגדרת נתיב לאישור בקשת משתמש - רק מנהל (Admin) מורשה לגשת
@app.route('/admin/requests', methods=['POST'])
@token_required
@roles_required('Admin')  # בדיקה שהמשתמש המבצע את הפעולה הוא אכן מנהל
def approve_user(current_user):
    # קבלת נתוני ה-JSON שנשלחו מהאנגולר (מכיל את ה-ID של המשתמש לאישור)
    data = request.get_json()

    # חילוץ ה-ID של המשתמש מתוך הנתונים
    user_id_to_approve = data.get('user_id')

    # בדיקה אם נשלח ID; אם לא, מחזירים שגיאה (Bad Request)
    if not user_id_to_approve:
        return jsonify({'message': 'Missing user_id'}), 400

    try:
        # חיפוש המשתמש הספציפי בבסיס הנתונים לפי ה-ID שהתקבל
        user_to_approve = User.query.get(user_id_to_approve)

        # אם המשתמש לא נמצא ב-DB, מחזירים שגיאה 404
        if not user_to_approve:
            return jsonify({'message': 'User not found'}), 404

        # עדכון התפקיד של המשתמש מ-Reader ל-Uploader
        user_to_approve.role = 'Uploader'

        # איפוס תאריך הבקשה ל-None כדי שהמשתמש יוסר מרשימת ה"ממתינים לאישור"
        user_to_approve.request_date = None

        # שמירת השינויים בבסיס הנתונים באופן סופי
        db.session.commit()

        # החזרת הודעת הצלחה הכוללת את המייל של המשתמש שאושר
        return jsonify({'message': f'User {user_to_approve.email} approved.'}), 200

    except Exception as e:
        # במידה וחלה תקלה בתהליך, מבצעים ביטול (Rollback) כדי לא להשאיר נתונים לא תקינים
        db.session.rollback()
        # החזרת שגיאת שרת כללית
        return jsonify({'message': 'Internal server error'}), 500


# הגדרת נתיב החיפוש בשיטת POST כדי לקבל רשימת נתונים גדולה בגוף הבקשה
@app.route('/search/ingredients', methods=['POST'])
def search_recipes_by_ingredients():
    # קבלת נתוני ה-JSON שנשלחו מה-Angular
    data = request.get_json()
    # שליפת רשימת המצרכים שהמשתמש הקליד (ברירת מחדל היא רשימה ריקה)
    user_inputs = data.get('ingredients', [])

    # שלב 1: הכנת נתוני המשתמש - יצירת סט (Set) של מילות חיפוש נקיות (אותיות קטנות וללא רווחים)
    user_set = set([t.strip().lower() for t in user_inputs if t.strip()])

    try:
        # שליפת כל המתכונים הקיימים במסד הנתונים
        all_recipes = Recipe.query.all()
        # רשימה ריקה שתכיל את המתכונים שנמצאו יחד עם הציון שלהם
        scored_recipes = []

        # מעבר בלולאה על כל מתכון ומתכון בבסיס הנתונים
        for recipe in all_recipes:
            # חילוץ שמות המצרכים של המתכון הנוכחי מה-DB והפיכתם לאותיות קטנות
            original_ingredients = [ing.product.strip().lower() for ing in recipe.ingredients]

            # יצירת סט זמני שישמור אילו מצרכים מהמתכון "נפגעו" על ידי החיפוש (תומך בחיפוש חלקי)
            matched_ingredients_set = set()
            # לולאה שעוברת על כל מילה שהמשתמש חיפש (למשל "סלמו")
            for term in user_set:
                # לולאה פנימית שבודקת כל מצרך במתכון (למשל "דג סלמון טרי")
                for full_ing in original_ingredients:
                    # בדיקה אם מילת החיפוש נמצאת בתוך השם המלא של המצרך
                    if term in full_ing:
                        # אם נמצאה התאמה, מוסיפים את השם המלא לסט ההתאמות
                        matched_ingredients_set.add(full_ing)

            # שלב 1 (המשך): המרת רשימת המצרכים המקורית של המתכון ל-Set (לפי ההנחיה)
            recipe_set = set(original_ingredients)

            # אם למתכון אין מצרכים בכלל, נדלג עליו כדי למנוע טעויות בחישוב
            if not recipe_set: continue

            # שלב 2: חישוב רכיבים משותפים (Intersection) באמצעות האופרטור &
            # אנו בודקים אילו מהמצרכים שסימנו כ"מתאימים" באמת קיימים במתכון המקורי
            common_matches = matched_ingredients_set & recipe_set

            # שלב 3: חישוב ציון ההתאמה (Matching Score)
            # הנוסחה: מספר המצרכים המשותפים שנמצאו חלקי סך כל המצרכים שהמתכון דורש
            match_score = len(common_matches) / len(recipe_set)

            # שלב 4: סינון ומיון - הוספת המתכון לרשימה רק אם יש לפחות 10% התאמה
            if match_score >= 0.1:
                # שליפת נתיבי התמונות המעובדות של המתכון
                paths = recipe.get_variations()
                # הוספת המתכון עם הנתונים הרלוונטיים והציון המחושב לאחוזים
                scored_recipes.append({
                    'id': recipe.id,  # מזהה המתכון
                    'title': recipe.title,  # שם המתכון
                    'score': round(match_score * 100, 1),  # ציון ההתאמה מעוגל (למשל 75.5)
                    # שליחת נתיב התמונה המעובדת (שחור-לבן/מטושטש) במידה וקיימת
                    'image_url': f'/uploads/{os.path.basename(paths[1]) if len(paths) > 1 else ""}',
                    # 'prep_time': recipe.prep_time  # זמן ההכנה של המתכון
                    'prep_time': getattr(recipe, 'prep_time', getattr(recipe, 'preparation_time', 0)),  # זמן ההכנה של המתכון
                    'type': recipe.type,
                    'author_email': recipe.author.email,  # שליפה מהטבלה המקושרת (Users)
                    'ingredients_count': len(recipe.ingredients)  # ספירת מספר המצרכים במתכון
                })

        # שלב 4 (המשך): מיון כל התוצאות מהציון הגבוה ביותר לנמוך ביותר
        scored_recipes.sort(key=lambda x: x['score'], reverse=True)
        # החזרת רשימת המתכונים הממוינת והמסוננת בפורמט JSON
        return jsonify(scored_recipes), 200

    except Exception as e:
        # במקרה של תקלה כלשהי, החזרת הודעת שגיאה כללית לשרת
        return jsonify({'message': str(e)}), 500
    
# פונקציה ליצירת מסד הנתונים וטבלת המשתמשים אם לא קיימים
def create_db_and_admin():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@example.com').first():
            admin_password_hash = bcrypt.generate_password_hash('Admin123!').decode('utf-8')
            admin_user = User(email='admin@example.com', password=admin_password_hash, role='Admin',
                              is_approved_uploader=True)
            admin_user.save()


if __name__ == '__main__':
    create_db_and_admin()
    app.run(debug=True, port=5000)
