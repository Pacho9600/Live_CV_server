from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from ..db import get_db
from ..models import User
from ..security import verify_password
from ..desktop_auth import store

router = APIRouter(tags=["desktop-login"])


def _page(error: str | None, state: str, redirect_uri: str, code_challenge: str, prefill: bool) -> str:
    # Minimal single-file HTML with small CSS + JS.
    # Includes requested: Example button, show/hide password, placeholder reset/email text.
    email_prefill = "example@demo.local" if prefill else ""
    pw_prefill = ""  # we fill password via Example button JS (requested: hidden inside Example button)
    err_html = f"<div class='error'>{error}</div>" if error else ""
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Desktop Login</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#0b1220; color:#e6eefc; margin:0; }}
    .wrap {{ max-width:520px; margin:48px auto; padding:22px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.10); border-radius:14px; }}
    h1 {{ margin:0 0 14px; font-size:22px; }}
    label {{ display:block; margin:12px 0 6px; color:#bcd0ff; }}
    input {{ width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); background:rgba(0,0,0,0.25); color:#e6eefc; }}
    .row {{ display:flex; gap:10px; margin-top:14px; }}
    button {{ padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.14); background:rgba(0,150,255,0.18); color:#e6eefc; cursor:pointer; }}
    button.secondary {{ background:rgba(255,255,255,0.06); }}
    .hint {{ margin-top:14px; color:#9fb2da; font-size:13px; line-height:1.35; }}
    .error {{ margin:12px 0; padding:10px 12px; border-radius:10px; background:rgba(255,0,0,0.10); border:1px solid rgba(255,0,0,0.25); }}
    .pwwrap {{ display:flex; gap:8px; }}
    .pwwrap input {{ flex:1; }}
    .pwwrap button {{ width:110px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Login (Desktop Browser Flow)</h1>
    {err_html}
    <form method="post" action="/desktop/login">
      <input type="hidden" name="state" value="{state}" />
      <input type="hidden" name="redirect_uri" value="{redirect_uri}" />
      <input type="hidden" name="code_challenge" value="{code_challenge}" />

      <label>Email</label>
      <input id="email" name="email" type="email" placeholder="Email" value="{email_prefill}" required />

      <label>Password</label>
      <div class="pwwrap">
        <input id="password" name="password" type="password" placeholder="Password" value="{pw_prefill}" required />
        <button type="button" class="secondary" id="toggle">Show</button>
      </div>

      <div class="row">
        <button type="submit">Login</button>
        <button type="button" class="secondary" id="example">Example</button>
      </div>

      <div class="hint">
        Reset password / Email verification:<br/>
        — here would go reset password/email flow —
      </div>
    </form>
  </div>

<script>
  let submitting = false;
  const form = document.querySelector("form");
  if (form) {{
    form.addEventListener("submit", () => {{ submitting = true; }});
  }}

  function notifyDesktopCanceled() {{
    if (submitting) return;
    try {{
      const redirectInput = document.querySelector("input[name=redirect_uri]");
      const stateInput = document.querySelector("input[name=state]");
      const redirectUri = redirectInput ? redirectInput.value : "";
      const state = stateInput ? stateInput.value : "";
      if (!redirectUri || !state) return;

      const u = new URL(redirectUri);
      u.searchParams.set("state", state);
      u.searchParams.set("cancel", "1");
      const url = u.toString();
      if (navigator.sendBeacon) {{
        navigator.sendBeacon(url, "");
      }} else {{
        fetch(url, {{
          method: "GET",
          mode: "no-cors",
          keepalive: true,
        }});
      }}
    }} catch (_) {{}}
  }}

  // Best-effort: when the user closes this tab, tell the desktop app to stop waiting.
  window.addEventListener("pagehide", notifyDesktopCanceled);
  window.addEventListener("beforeunload", notifyDesktopCanceled);

  const pw = document.getElementById("password");
  const toggle = document.getElementById("toggle");
  toggle.addEventListener("click", () => {{
    const isPw = pw.getAttribute("type") === "password";
    pw.setAttribute("type", isPw ? "text" : "password");
    toggle.textContent = isPw ? "Hide" : "Show";
  }});

  document.getElementById("example").addEventListener("click", () => {{
    document.getElementById("email").value = "example@demo.local";
    // hidden inside Example button: we fill it here on click
    pw.value = "Demo" + "Pass" + "123" + "!";
  }});
</script>
</body>
</html>"""

@router.get("/desktop/login", response_class=HTMLResponse)
def desktop_login_page(state: str, redirect_uri: str, code_challenge: str, prefill: int = 0):
    # Register pending login request (state + redirect + challenge).
    store.register_pending(state=state, redirect_uri=redirect_uri, code_challenge=code_challenge)
    return _page(error=None, state=state, redirect_uri=redirect_uri, code_challenge=code_challenge, prefill=bool(prefill))


@router.post("/desktop/login")
def desktop_login_submit(
    email: str = Form(...),
    password: str = Form(...),
    state: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    db: Session = Depends(get_db),
):
    # Ensure pending request exists and parameters match.
    pending = store.get_pending(state)
    if not pending or pending.redirect_uri != redirect_uri or pending.code_challenge != code_challenge:
        # Render again with error
        return HTMLResponse(_page("Invalid login session. Please restart login from the desktop app.", state, redirect_uri, code_challenge, prefill=False), status_code=400)

    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse(_page("Invalid credentials.", state, redirect_uri, code_challenge, prefill=False), status_code=401)

    # Issue one-time auth code and redirect back to the desktop callback URL.
    auth_code = store.issue_code(state=state, user_id=user.id)

    qs = urlencode({"code": auth_code.code, "state": state})
    return RedirectResponse(url=f"{redirect_uri}?{qs}", status_code=302)
