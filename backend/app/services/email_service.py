import aiosmtplib
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template

from app.config import get_settings

settings = get_settings()

LISTING_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; margin: 0; padding: 20px; }
    .container { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
    .header { background: linear-gradient(135deg, #1877f2, #0d5bbd); color: white; padding: 24px 32px; }
    .header h1 { margin: 0; font-size: 22px; font-weight: 600; }
    .header p { margin: 8px 0 0; opacity: 0.9; font-size: 14px; }
    .score-badge { display: inline-block; background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-top: 12px; }
    .image { width: 100%; max-height: 300px; object-fit: cover; }
    .content { padding: 24px 32px; }
    .price { font-size: 28px; font-weight: 700; color: #1877f2; margin: 0 0 8px; }
    .title { font-size: 20px; font-weight: 600; color: #1c1e21; margin: 0 0 16px; }
    .details { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 20px 0; }
    .detail-item { background: #f0f2f5; padding: 12px 16px; border-radius: 8px; }
    .detail-label { font-size: 11px; text-transform: uppercase; color: #65676b; letter-spacing: 0.5px; }
    .detail-value { font-size: 15px; font-weight: 600; color: #1c1e21; margin-top: 4px; }
    .cta { display: block; text-align: center; background: #1877f2; color: white !important; text-decoration: none; padding: 14px 24px; border-radius: 8px; font-weight: 600; margin-top: 24px; }
    .footer { padding: 16px 32px; background: #f0f2f5; text-align: center; font-size: 12px; color: #65676b; }
  </style>
</head>
<body>
    <div class="container">
    {% if is_demo %}
    <div style="background:#fff3cd;color:#856404;text-align:center;padding:12px 16px;font-size:14px;font-weight:600;border-bottom:1px solid #ffeeba;">
      ⚠️ Demo test email — sample listing preview (not a real alert)
    </div>
    {% endif %}
    <div class="header">
      <h1>🚗 New Vehicle Match Found!</h1>
      <p>A listing matching your criteria was detected on Facebook Marketplace</p>
      <span class="score-badge">Match Score: {{ match_score }}%</span>
    </div>
    {% if image_url %}
    <img class="image" src="{{ image_url }}" alt="{{ title }}">
    {% endif %}
    <div class="content">
      <p class="price">{{ currency }} {{ price }}</p>
      <h2 class="title">{{ title }}</h2>
      <div class="details">
        {% if brand %}<div class="detail-item"><div class="detail-label">Brand</div><div class="detail-value">{{ brand }}</div></div>{% endif %}
        {% if model %}<div class="detail-item"><div class="detail-label">Model</div><div class="detail-value">{{ model }}</div></div>{% endif %}
        {% if fuel_type %}<div class="detail-item"><div class="detail-label">Fuel</div><div class="detail-value">{{ fuel_type }}</div></div>{% endif %}
        {% if transmission %}<div class="detail-item"><div class="detail-label">Transmission</div><div class="detail-value">{{ transmission }}</div></div>{% endif %}
        {% if mileage %}<div class="detail-item"><div class="detail-label">Mileage</div><div class="detail-value">{{ mileage }} km</div></div>{% endif %}
        {% if year %}<div class="detail-item"><div class="detail-label">Year</div><div class="detail-value">{{ year }}</div></div>{% endif %}
        {% if location %}<div class="detail-item"><div class="detail-label">Location</div><div class="detail-value">{{ location }}</div></div>{% endif %}
        {% if filter_name %}<div class="detail-item"><div class="detail-label">Filter</div><div class="detail-value">{{ filter_name }}</div></div>{% endif %}
      </div>
      {% if score_breakdown %}
      <p style="font-size:13px;color:#65676b;margin:16px 0 0;">Match breakdown: {{ score_breakdown }}</p>
      {% endif %}
      {% if description %}
      <p style="font-size:14px;color:#1c1e21;margin:16px 0 0;line-height:1.5;">{{ description }}</p>
      {% endif %}
      <a class="cta" href="{{ listing_url }}">View Listing on Facebook →</a>
    </div>
    <div class="footer">
      {% if is_demo %}
      Facebook Marketplace Monitor · Demo test email — SMTP and alert format check
      {% else %}
      Facebook Marketplace Monitor · Automated Vehicle Alert
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

DEMO_LISTING_EMAIL_DATA = {
    "title": "2018 VW Golf 1.4 TSI DSG – Serviceheft, MFK 2026",
    "price": "5,500",
    "currency": "CHF",
    "mileage": 98000,
    "year": 2018,
    "brand": "Volkswagen",
    "model": "Golf",
    "fuel_type": "Petrol",
    "transmission": "DSG Automatic",
    "location": "Zurich, ZH",
    "posted_time": "Recently",
    "match_score": 92,
    "filter_name": "Zurich Vehicle Search",
    "score_breakdown": "brand: 100%, model: 100%, fuel_type: 100%, transmission: 100%, location: 90%",
    "description": "Demo listing — this is how real match alerts will look when the bot finds a vehicle on Facebook Marketplace.",
    "listing_url": "https://www.facebook.com/marketplace/",
    "image_url": None,
    "is_demo": True,
}


class EmailService:
    def __init__(self):
        self.settings = get_settings()

    def _get_smtp_config(self, db_settings: dict | None = None) -> dict:
        db_settings = db_settings or {}
        return {
            "host": db_settings.get("smtp_host") or self.settings.SMTP_HOST,
            "port": int(db_settings.get("smtp_port") or self.settings.SMTP_PORT),
            "username": db_settings.get("smtp_user") or self.settings.SMTP_USER,
            "password": db_settings.get("smtp_password") or self.settings.SMTP_PASSWORD,
            "from_email": db_settings.get("smtp_from_email") or self.settings.SMTP_FROM_EMAIL or self.settings.SMTP_USER,
            "from_name": db_settings.get("smtp_from_name") or self.settings.SMTP_FROM_NAME,
            "use_tls": (db_settings.get("smtp_use_tls", "true")).lower() == "true",
        }

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        smtp_config: dict | None = None,
    ) -> tuple[bool, str]:
        config = self._get_smtp_config(smtp_config)
        if not config["username"] or not config["password"]:
            return False, "SMTP not configured. Administrator must set SMTP_USER and SMTP_PASSWORD in backend .env file."

        message = MIMEMultipart("alternative")
        message["From"] = f"{config['from_name']} <{config['from_email']}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        try:
            await asyncio.wait_for(
                aiosmtplib.send(
                    message,
                    hostname=config["host"],
                    port=config["port"],
                    username=config["username"],
                    password=config["password"],
                    start_tls=config["use_tls"],
                    timeout=15,
                ),
                timeout=20,
            )
            return True, "Email sent successfully"
        except Exception as exc:
            return False, str(exc)

    async def send_listing_notification(
        self,
        to_email: str,
        listing_data: dict,
        smtp_config: dict | None = None,
    ) -> tuple[bool, str]:
        template = Template(LISTING_EMAIL_TEMPLATE)
        html = template.render(**listing_data)
        subject = f"🚗 New Match: {listing_data.get('title', 'Vehicle')} - {listing_data.get('currency', 'CHF')} {listing_data.get('price', '')}"
        return await self.send_email(to_email, subject, html, smtp_config)

    async def send_test_email(self, to_email: str, smtp_config: dict | None = None) -> tuple[bool, str]:
        demo = dict(DEMO_LISTING_EMAIL_DATA)
        template = Template(LISTING_EMAIL_TEMPLATE)
        html = template.render(**demo)
        title = demo.get("title", "Vehicle")
        subject = f"🚗 [DEMO] New Match: {title} - {demo.get('currency', 'CHF')} {demo.get('price', '')}"
        ok, result = await self.send_email(to_email, subject, html, smtp_config)
        if ok:
            return True, "Demo alert email sent (same format as real match notifications)"
        return ok, result


email_service = EmailService()
