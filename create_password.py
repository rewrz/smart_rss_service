# create_password.py
from werkzeug.security import generate_password_hash
import getpass

password = getpass.getpass("请输入你的管理员密码: ")
hashed_password = generate_password_hash(password)
print("\n请将下面这行内容复制到你的 .env 文件中:")
print(f'ADMIN_PASSWORD_HASH="{hashed_password}"')
