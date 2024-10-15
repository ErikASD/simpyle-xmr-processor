from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
import models
from database import SessionLocal, engine
import uvicorn
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pgplogin import PGPLogin
import jwt
import json
from deposit import Deposit
from withdraw import Withdraw
import asyncio
import base64

models.Base.metadata.create_all(bind=engine)

with open('config.json', 'r') as file:
	config = json.load(file)

with open('secrets.json', 'r') as file:
	server_secrets = json.load(file)

app = FastAPI()
pgp_login = PGPLogin(server_secrets["CONF_PEPPER"])
deposit = Deposit()
withdraw = Withdraw(config)

template = Jinja2Templates(directory="templates").TemplateResponse

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

def get_jwt_token(user_id):
	encoded_jwt = jwt.encode({"user_id": user_id}, server_secrets["JWT_SECRET"], algorithm="HS256")
	return encoded_jwt

def get_user(db, request):
	encoded_jwt = request.cookies.get("auth")
	if not encoded_jwt:
		return None
	try:
		user_id = jwt.decode(encoded_jwt, server_secrets["JWT_SECRET"], algorithms=["HS256"])["user_id"]
	except:
		return None

	user = models.User.get(db, user_id)
	return user

class BackgroundRunner:
	def __init__(self):
		self.db = next(get_db())

	async def run_delete_old_login_codes(self):
		while True:
			models.LoginCode.delete_expired(self.db, config["LOGIN_CODE_EXPIRE_TIME"])
			await asyncio.sleep(config["LOGIN_CODE_SWEEP_TIME"])

	async def run_check_deposits(self):
		while True:
			try:
				print("checking deposits")
				deposit.check_deposits(self.db)
			except Exception as e:
				print(str(e))
			await asyncio.sleep(config["DEPOSIT_SWEEP_TIME"])

runner = BackgroundRunner()

@app.on_event('startup')
async def app_startup():
	asyncio.create_task(runner.run_delete_old_login_codes())
	asyncio.create_task(runner.run_check_deposits())

@app.get("/")
async def path_root(request: Request, db: Session = Depends(get_db)):
	return RedirectResponse("/user/login", status_code=302)

@app.get("/user")
async def path_user(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if not user:
		return RedirectResponse("/user/login", status_code=302)

	return template(request=request, name="user/user.html", context={"user":user,"page":"user"})

@app.get("/user/login")
async def path_user_login(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if user:
		return RedirectResponse("/user", status_code=302)

	return template(request=request, name="user/login.html", context={})

@app.post("/user/login")
async def path_user_login_post(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if user:
		return RedirectResponse("/user", status_code=302)

	form = await request.form()
	public_pgp_key = form.get("public_pgp")

	if not public_pgp_key:
		return "No public PGP key provided"

	fingerprint, confirmation_code, encrypted_data = pgp_login.generate_encrypted_confirmation_code(public_pgp_key)
	
	if not fingerprint:
		return RedirectResponse("/user/login", status_code=302)

	login_code = pgp_login.create_login_code_in_db(db, fingerprint, confirmation_code)
	return template(request=request, name="user/code-display.html", context={"message":encrypted_data.data,"public_pgp_key":public_pgp_key})

@app.post("/user/login/verify")
async def path_user_login_verify(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if user:
		return RedirectResponse("/user", status_code=302)

	form = await request.form()
	code = form.get("code")
	public_pgp_key = form.get("public_pgp")

	login_code, display_name, fingerprint = pgp_login.verify_login_code(db, public_pgp_key, code)

	if not login_code:
		return RedirectResponse("/user/login", status_code=302)

	if login_code.user:
		db_user = models.User.login(login_code)
	else:
		db_user = models.User.create(db, display_name, fingerprint, login_code)

	if not db_user:
		return RedirectResponse("/user/login", status_code=302)

	response = RedirectResponse("/user", status_code=302)
	response.set_cookie("auth", get_jwt_token(db_user.id), max_age=86400 * 365)
	return response

@app.get("/user/logout")
async def path_user_logout(request: Request, db: Session = Depends(get_db)):
    response = RedirectResponse("/")
    response.delete_cookie("auth")
    return response

@app.get("/user/deposit")
async def path_user_deposit(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if not user:
		return RedirectResponse("/user/login", status_code=302)

	deposit.create_deposit_if_none(db, user)
	return template(request=request, name="user/deposit.html", context={"user":user,"page":"deposit", "deposit":deposit})

@app.get("/user/withdraw")
async def path_user_withdraw(request: Request, result: str = "", db: Session = Depends(get_db)):
	user = get_user(db, request)
	if not user:
		return RedirectResponse("/user/login", status_code=302)

	return template(request=request, name="user/withdraw.html", context={"user":user,"page":"withdraw","result":base64.b64decode(result.encode()).decode()})

@app.post("/user/withdraw")
async def path_user_withdraw_post(request: Request, db: Session = Depends(get_db)):
	user = get_user(db, request)
	if not user:
		return RedirectResponse("/user/login", status_code=302)

	form = await request.form()
	address = form.get("address")
	amount = form.get("amount")
	if float(amount) < 0.0001:
		transfer_final = 'amount has to be greater than 0.0001'
	else:
		transfer_final = withdraw.request_withdraw(db, user, amount, address)
	return RedirectResponse(f"/user/withdraw?result={base64.b64encode(transfer_final.encode()).decode()}", status_code=302)

if __name__ == "__main__":
	uvicorn.run("main:app", host=config["HOST"], port=config["PORT"], reload=config["LIVE_RELOAD"])