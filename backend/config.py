import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://sammy:Pompilo%4017@localhost/sales_crm'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.urandom(24)
