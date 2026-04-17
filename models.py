from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import json # נשתמש בזה לשמירת variation_paths כ-JSON

# יצירת אובייקט ה-DB שבו נשתמש גם ב-app.py
db = SQLAlchemy()


# --- מחלקת הבסיס (BaseModel) ---
class BaseModel(db.Model):
    """
    מחלקה אבסטרקטית שמגדירה את עמודת ה-ID ופעולת השמירה
    עבור כל הטבלאות במערכת.
    """
    # אומר ל-SQLAlchemy לא ליצור טבלה עבור המחלקה הזו ב-DB, אלא רק להוריש את התכונות שלה למחלקות הבנות.
    __abstract__ = True  # אומר ל-SQLAlchemy לא ליצור טבלה עבור המחלקה הזו, אלא רק עבור היורשים
    # עמודת מזהה יחיד לכל רשומה. db.Column מגדיר עמודה בטבלה. primary_key=True מגדיר את העמודה כמפתח ראשי ומוודא שהיא ייחודית.
    id = db.Column(db.Integer, primary_key=True)

    def save(self):
        """שומר את האובייקט הנוכחי למסד הנתונים"""
        db.session.add(self)  # מוסיף את אובייקט הפייתון הנוכחי (self) ל-"סשן" (הקשר) של מסד הנתונים.
        db.session.commit()  # מבצע את השינויים בסשן ושומר אותם לצמיתות ב-DB.


# --- מודל משתמש (User) ---
class User(BaseModel):# יורש מ-BaseModel, ולכן מקבל אוטומטית את עמודת ה-ID ואת מתודת save().
    __tablename__ = 'users'# שם הטבלה במסד הנתונים יהיה 'users'.
#בדיקות תקינות
    email = db.Column(db.String(120), unique=True,nullable=False)  # עמודת מייל. String(120) מגביל את אורכה ל-120 תווים. unique=True אוכף שלא יהיו שני מיילים זהים. nullable=False אומר שערך זה חובה.
    password = db.Column(db.String(200), nullable=False)  # עמודת הסיסמה המגובבת. אורך 200 מספיק לגיבוב Bcrypt.
    role = db.Column(db.String(20), default='Reader')  # תפקיד המשתמש (Admin, Uploader, Reader). default='Reader' מגדיר את ערך ברירת המחדל.
    is_approved_uploader = db.Column(db.Boolean, default=False)  # שדה בוליאני (True/False) שמציין האם המשתמש אושר להעלות מתכונים.
    request_date = db.Column(db.DateTime, nullable=True)   # שדה שמתעד את זמן בקשת ההרשאה. כברירת מחדל הוא ריק (None)
    recipes = db.relationship('Recipe', backref='author', lazy=True)# קשר למתכונים שהמשתמש העלה (אופציונלי, עוזר לשלוף מתכונים של משתמש)
# backref='author': מוסיף באופן אוטומטי עמודה בשם 'author' למחלקת Recipe, המפנה לאובייקט המשתמש.
    # lazy=True: טוען את רשימת המתכונים רק כשצריך (טעינה עצלה).

# --- מודל מתכון (Recipe) ---
class Recipe(BaseModel):
    __tablename__ = 'recipes'

    title = db.Column(db.String(100), nullable=False)  # שם המתכון.
    description = db.Column(db.Text, nullable=True)  # עמודת טקסט ארוך להוראות הכנה.
    image_path = db.Column(db.String(200), nullable=False)  # נתיב לקובץ התמונה המקורי (בתיקיית uploads).
    variation_paths = db.Column(db.Text, nullable=True)  # עמודת טקסט לשמירת נתיבי 3 תמונות הווריאציה. יישמר כ-JSON String.
    type = db.Column(db.String(20), nullable=False)  # סוג המתכון: Dairy, Meat, Parve.
    prep_time = db.Column(db.Integer, default=0)  # זמן הכנה בדקות
    # מפתח זר למשתמש שיצר את המתכון
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # קשר לרכיבים (One-to-Many - מתכון אחד יכול להכיל רשימת רכיבים רבים)
    # קשר מטבלת Recipe לטבלת IngredientEntry.
    ingredients = db.relationship('IngredientEntry', backref='recipe', lazy=True, cascade="all, delete-orphan")
    # cascade="all, delete-orphan": הגדרה חשובה: אם מתכון נמחק, כל רשומות ה-IngredientEntry המקושרות אליו נמחקות אוטומטית (ניקיון DB).

    def set_variations(self, paths_list):
        """פונקציית עזר לשמירת רשימת הנתיבים כ-JSON"""
        self.variation_paths = json.dumps(paths_list)

    def get_variations(self):
        """פונקציית עזר לקבלת הנתיבים כרשימה"""
        if self.variation_paths:
            return json.loads(self.variation_paths)
        return []


# --- מודל רכיב (IngredientEntry) ---
class IngredientEntry(BaseModel):
    __tablename__ = 'ingredients'

    product = db.Column(db.String(100), nullable=False)  # שם הרכיב (קמח, ביצים)
    amount = db.Column(db.Float, nullable=False)  # כמות (1.5)
    unit = db.Column(db.String(50), nullable=False)  # יחידה (כוס, גרם)

    # מפתח זר למתכון
    # זהו המפתח הזר שמקשר כל רכיב למתכון ספציפי (דרוש לקשר One-to-Many).
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)