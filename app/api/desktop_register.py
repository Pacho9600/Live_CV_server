from __future__ import annotations

import datetime as dt
import html

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import RegistrationSession, User, UserProfile
from ..security import hash_password
from ..settings import settings

try:
    import stripe  # type: ignore
except Exception:  # pragma: no cover
    stripe = None  # type: ignore[assignment]


router = APIRouter(tags=["desktop-register"])


def _wrap_page(*, title: str, body_html: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{safe_title}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#0b1220; color:#e6eefc; margin:0; }}
    .wrap {{ max-width:760px; margin:48px auto; padding:22px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.10); border-radius:14px; }}
    h1 {{ margin:0 0 8px; font-size:22px; }}
    h2 {{ margin:18px 0 8px; font-size:16px; color:#bcd0ff; }}
    .muted {{ color:#9fb2da; font-size:13px; line-height:1.35; }}
    label {{ display:block; margin:12px 0 6px; color:#bcd0ff; }}
    input {{ width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); background:rgba(0,0,0,0.25); color:#e6eefc; }}
    .row {{ display:flex; gap:10px; margin-top:14px; flex-wrap:wrap; }}
    button, a.btn {{ padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.14); background:rgba(0,150,255,0.18); color:#e6eefc; cursor:pointer; text-decoration:none; display:inline-block; }}
    button.secondary, a.btn.secondary {{ background:rgba(255,255,255,0.06); }}
    .error {{ margin:12px 0; padding:10px 12px; border-radius:10px; background:rgba(255,0,0,0.10); border:1px solid rgba(255,0,0,0.25); }}
    .card {{ margin-top:14px; padding:12px; border-radius:10px; background:rgba(0,0,0,0.22); border:1px solid rgba(255,255,255,0.10); }}
    .kv {{ display:grid; grid-template-columns: 160px 1fr; gap:8px 12px; font-size:14px; }}
    .kv div {{ padding:2px 0; }}
  </style>
</head>
<body>
  <div class="wrap">
    {body_html}
  </div>
</body>
</html>"""


def _error_box(msg: str | None) -> str:
    if not msg:
        return ""
    return f"<div class='error'>{html.escape(msg)}</div>"


def _safe(v: str | None) -> str:
    return html.escape(v or "")


def _data_page(*, error: str | None, values: dict[str, str] | None = None) -> str:
    values = values or {}
    body = f"""
    <h1>Registration</h1>
    <div class="muted">Step 1/5: Data</div>
    {_error_box(error)}
    <form method="post" action="/desktop/register">
      <div class="row">
        <button type="button" class="secondary" id="example">Example</button>
      </div>

      <label>First name</label>
      <input id="first_name" name="first_name" placeholder="First name" value="{_safe(values.get('first_name'))}" required />

      <label>Last name</label>
      <input id="last_name" name="last_name" placeholder="Last name" value="{_safe(values.get('last_name'))}" required />

      <label>Address</label>
      <input id="address" name="address" placeholder="Address" value="{_safe(values.get('address'))}" required />

      <label>Country</label>
      <input id="country" name="country" placeholder="Country" value="{_safe(values.get('country'))}" required />

      <label>Email</label>
      <input id="email" name="email" type="email" placeholder="Email" value="{_safe(values.get('email'))}" required />

      <label>Password</label>
      <input id="password" name="password" type="password" placeholder="Password" value="" required />

      <div class="row">
        <button type="submit">Next</button>
      </div>
    </form>

    <script>
      document.getElementById("example").addEventListener("click", () => {{
        document.getElementById("first_name").value = "Ada";
        document.getElementById("last_name").value = "Lovelace";
        document.getElementById("address").value = "123 Demo Street";
        document.getElementById("country").value = "United States";
        document.getElementById("email").value = "ada@example.demo";
        document.getElementById("password").value = "Demo" + "Pass" + "123" + "!";
      }});
    </script>
    """
    return _wrap_page(title="Registration - Data", body_html=body)


def _placeholder_page(*, step: int, title: str, reg_id: str, text: str) -> str:
    body = f"""
    <h1>Registration</h1>
    <div class="muted">Step {step}/5: {html.escape(title)}</div>
    <div class="card">
      <div class="muted">{html.escape(text)}</div>
    </div>
    <form method="post">
      <input type="hidden" name="reg" value="{html.escape(reg_id)}" />
      <div class="row">
        <button type="submit">Next</button>
        <a class="btn secondary" href="/desktop/register/cancel?reg={html.escape(reg_id)}">Cancel</a>
      </div>
    </form>
    """
    return _wrap_page(title=f"Registration - {title}", body_html=body)


def _get_reg(db: Session, reg_id: str) -> RegistrationSession | None:
    return db.get(RegistrationSession, reg_id)


def _cancel_and_delete(db: Session, reg: RegistrationSession) -> None:
    user = db.get(User, reg.user_id)
    if not user:
        db.delete(reg)
        db.commit()
        return

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile:
        db.delete(profile)
    db.delete(reg)
    db.delete(user)
    db.commit()


@router.get("/desktop/register", response_class=HTMLResponse)
def register_page() -> str:
    return _data_page(error=None)


@router.post("/desktop/register")
def register_submit(
    first_name: str = Form(...),
    last_name: str = Form(...),
    address: str = Form(...),
    country: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = email.strip().lower()
    if not email_norm:
        return HTMLResponse(_data_page(error="Email is required."), status_code=status.HTTP_400_BAD_REQUEST)

    existing = db.query(User).filter(User.email == email_norm).first()
    if existing:
        vals = {"first_name": first_name, "last_name": last_name, "address": address, "country": country, "email": email_norm}
        return HTMLResponse(_data_page(error="Email already registered.", values=vals), status_code=status.HTTP_400_BAD_REQUEST)

    user = User(email=email_norm, password_hash=hash_password(password), role="user")
    profile = UserProfile(
        user_id=0,  # set after flush
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        address=address.strip(),
        country=country.strip(),
    )
    reg = RegistrationSession(user_id=0, step=2)

    try:
        db.add(user)
        db.flush()  # assigns user.id
        profile.user_id = user.id
        reg.user_id = user.id
        db.add(profile)
        db.add(reg)
        db.commit()
    except IntegrityError:
        db.rollback()
        vals = {"first_name": first_name, "last_name": last_name, "address": address, "country": country, "email": email_norm}
        return HTMLResponse(_data_page(error="Could not create user (email may already exist).", values=vals), status_code=status.HTTP_400_BAD_REQUEST)

    return RedirectResponse(url=f"/desktop/register/email?reg={reg.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/desktop/register/cancel", response_class=HTMLResponse)
def register_cancel(reg: str, db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if reg_obj:
        if reg_obj.status == "completed":
            body = """
            <h1>Registration already completed</h1>
            <div class="muted">This registration is already completed and can no longer be canceled.</div>
            """
            return _wrap_page(title="Registration complete", body_html=body)
        _cancel_and_delete(db, reg_obj)

    body = """
    <h1>Registration canceled</h1>
    <div class="muted">Your registration was canceled and any temporary data was removed.</div>
    <div class="row" style="margin-top:18px;">
      <a class="btn" href="/desktop/register">Start again</a>
    </div>
    """
    return _wrap_page(title="Registration canceled", body_html=body)


@router.get("/desktop/register/email", response_class=HTMLResponse)
def register_email_page(reg: str, db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    return _placeholder_page(
        step=2,
        title="Email verification",
        reg_id=reg_obj.id,
        text="Here comes the email verification step. In a real system we would send a one-time link to confirm account ownership.",
    )


@router.post("/desktop/register/email")
def register_email_next(reg: str = Form(...), db: Session = Depends(get_db)):
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return HTMLResponse(_wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>"), status_code=400)

    user = db.get(User, reg_obj.user_id)
    if user and user.email_verified_at is None:
        user.email_verified_at = dt.datetime.now(dt.timezone.utc)

    reg_obj.step = max(reg_obj.step, 3)
    db.commit()
    return RedirectResponse(url=f"/desktop/register/2fa?reg={reg_obj.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/desktop/register/2fa", response_class=HTMLResponse)
def register_2fa_page(reg: str, db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    return _placeholder_page(
        step=3,
        title="2FA verification",
        reg_id=reg_obj.id,
        text="Here comes the 2FA step. This would confirm the user via a second factor (TOTP/SMS/Push) to make the account more secure.",
    )


@router.post("/desktop/register/2fa")
def register_2fa_next(reg: str = Form(...), db: Session = Depends(get_db)):
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return HTMLResponse(_wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>"), status_code=400)

    reg_obj.step = max(reg_obj.step, 4)
    db.commit()
    return RedirectResponse(url=f"/desktop/register/payment?reg={reg_obj.id}", status_code=status.HTTP_303_SEE_OTHER)


def _stripe_ready() -> tuple[bool, str | None]:
    if not settings.STRIPE_SECRET_KEY:
        return False, "Stripe is not configured. Set STRIPE_SECRET_KEY in your .env."
    if stripe is None:
        return False, "Stripe package is not installed. Install it with: pip install -r requirements.txt"
    return True, None


@router.get("/desktop/register/payment", response_class=HTMLResponse)
def register_payment_page(reg: str, db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    ready, stripe_err = _stripe_ready()
    paid = bool(reg_obj.paid_at)

    err_html = _error_box(stripe_err) if not ready else ""
    paid_html = "<div class='card'><div class='muted'>Payment status: PAID</div></div>" if paid else ""

    body = f"""
    <h1>Registration</h1>
    <div class="muted">Step 4/5: Payment</div>
    {err_html}
    {paid_html}
    <div class="card">
      <div class="muted">Payment is handled via Stripe Checkout (test mode). After payment you will be returned here.</div>
    </div>

    <form method="post" action="/desktop/register/payment">
      <input type="hidden" name="reg" value="{html.escape(reg_obj.id)}" />
      <div class="row">
        <button type="submit" {'disabled' if not ready else ''}>Pay with Stripe</button>
        <a class="btn secondary" href="/desktop/register/cancel?reg={html.escape(reg_obj.id)}">Cancel</a>
        <a class="btn secondary" href="/desktop/register/review?reg={html.escape(reg_obj.id)}" {'style="opacity:.6; pointer-events:none;"' if not paid else ''}>Next</a>
      </div>
      <div class="muted" style="margin-top:10px;">Price: {settings.STRIPE_UNIT_AMOUNT/100:.2f} {html.escape(settings.STRIPE_CURRENCY.upper())}</div>
    </form>
    """
    return _wrap_page(title="Registration - Payment", body_html=body)


@router.post("/desktop/register/payment")
def register_payment_start(request: Request, reg: str = Form(...), db: Session = Depends(get_db)):
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return HTMLResponse(_wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>"), status_code=400)

    ready, stripe_err = _stripe_ready()
    if not ready:
        return HTMLResponse(_wrap_page(title="Stripe error", body_html=f"<h1>Payment unavailable</h1>{_error_box(stripe_err)}"), status_code=400)

    stripe.api_key = settings.STRIPE_SECRET_KEY  # type: ignore[union-attr]

    base = str(request.base_url).rstrip("/") if request else ""
    success_url = f"{base}/desktop/register/payment/success?reg={reg_obj.id}&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base}/desktop/register/cancel?reg={reg_obj.id}"

    session = stripe.checkout.Session.create(  # type: ignore[union-attr]
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY,
                    "product_data": {"name": settings.STRIPE_PRODUCT_NAME},
                    "unit_amount": settings.STRIPE_UNIT_AMOUNT,
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"registration_id": reg_obj.id, "user_id": str(reg_obj.user_id)},
    )

    reg_obj.stripe_checkout_session_id = session.get("id")
    db.commit()

    url = session.get("url")
    if not url:
        return HTMLResponse(_wrap_page(title="Stripe error", body_html="<h1>Stripe session missing URL.</h1>"), status_code=500)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/desktop/register/payment/success", response_class=HTMLResponse)
def register_payment_success(reg: str, session_id: str | None = None, db: Session = Depends(get_db)):
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    ready, stripe_err = _stripe_ready()
    if not ready:
        return _wrap_page(title="Stripe error", body_html=f"<h1>Payment verification unavailable</h1>{_error_box(stripe_err)}")

    if not session_id:
        return _wrap_page(title="Stripe error", body_html="<h1>Missing Stripe session_id.</h1>")

    stripe.api_key = settings.STRIPE_SECRET_KEY  # type: ignore[union-attr]
    try:
        sess = stripe.checkout.Session.retrieve(session_id)  # type: ignore[union-attr]
    except Exception as e:
        return _wrap_page(title="Stripe error", body_html=f"<h1>Could not verify payment.</h1>{_error_box(str(e))}")

    if sess.get("payment_status") != "paid":
        return _wrap_page(
            title="Payment not completed",
            body_html="<h1>Payment not completed.</h1><div class='row' style='margin-top:18px;'><a class='btn' href='/desktop/register/payment?reg="
            + html.escape(reg_obj.id)
            + "'>Back to payment</a></div>",
        )

    reg_obj.paid_at = dt.datetime.now(dt.timezone.utc)
    reg_obj.step = max(reg_obj.step, 5)
    reg_obj.stripe_checkout_session_id = session_id
    db.commit()

    return RedirectResponse(url=f"/desktop/register/review?reg={reg_obj.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/desktop/register/review", response_class=HTMLResponse)
def register_review_page(reg: str, db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    user = db.get(User, reg_obj.user_id)
    profile = db.query(UserProfile).filter(UserProfile.user_id == reg_obj.user_id).first()
    if not user or not profile:
        return _wrap_page(title="Registration error", body_html="<h1>Registration data missing.</h1>")

    paid = bool(reg_obj.paid_at)
    body = f"""
    <h1>Registration</h1>
    <div class="muted">Step 5/5: Review</div>

    <h2>Account</h2>
    <div class="card">
      <div class="kv">
        <div>Email</div><div>{html.escape(user.email)}</div>
        <div>Email verified</div><div>{'Yes' if user.email_verified_at else 'No (placeholder step)'}</div>
        <div>2FA</div><div>Placeholder (not implemented)</div>
        <div>Payment</div><div>{'PAID' if paid else 'NOT PAID'}</div>
      </div>
    </div>

    <h2>Profile</h2>
    <div class="card">
      <div class="kv">
        <div>First name</div><div>{html.escape(profile.first_name)}</div>
        <div>Last name</div><div>{html.escape(profile.last_name)}</div>
        <div>Address</div><div>{html.escape(profile.address)}</div>
        <div>Country</div><div>{html.escape(profile.country)}</div>
      </div>
    </div>

    <form method="post" action="/desktop/register/complete">
      <input type="hidden" name="reg" value="{html.escape(reg_obj.id)}" />
      <div class="row">
        <button type="submit" {'disabled' if not paid else ''}>Complete</button>
        <a class="btn secondary" href="/desktop/register/cancel?reg={html.escape(reg_obj.id)}">Cancel</a>
        <a class="btn secondary" href="/desktop/register/payment?reg={html.escape(reg_obj.id)}">Back</a>
      </div>
      {'<div class=\"muted\" style=\"margin-top:10px;\">Complete is disabled until payment is marked as PAID.</div>' if not paid else ''}
    </form>
    """
    return _wrap_page(title="Registration - Review", body_html=body)


@router.post("/desktop/register/complete", response_class=HTMLResponse)
def register_complete(reg: str = Form(...), db: Session = Depends(get_db)) -> str:
    reg_obj = _get_reg(db, reg)
    if not reg_obj:
        return _wrap_page(title="Registration error", body_html="<h1>Invalid registration session.</h1>")

    if not reg_obj.paid_at:
        return _wrap_page(title="Registration error", body_html="<h1>Payment is required before completing registration.</h1>")

    reg_obj.status = "completed"
    reg_obj.step = max(reg_obj.step, 5)
    db.commit()

    body = """
    <h1>Registration complete</h1>
    <div class="muted">Your account is created. Return to the desktop app and click "Login in Browser" to sign in.</div>
    <div class="row" style="margin-top:18px;">
      <a class="btn" href="/desktop/register">Create another account</a>
    </div>
    """
    return _wrap_page(title="Registration complete", body_html=body)
