# cron_monitor.py
import os
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
import requests
from affiliate_links import generate_aviasales_search_url


# 1. 引入 dotenv
from dotenv import load_dotenv

# 2. 載入 .env 變數
load_dotenv()
# 讀取與 cron_monitor.py 同目錄下的 monitors.json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONITOR_FILE = os.path.join(BASE_DIR, 'monitors.json')
SENT_ALERTS_FILE = os.path.join(BASE_DIR, 'sent_alerts.json')

def is_valid_email(email):
    if not email:
        return False
    return re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email) is not None

def load_sent_alerts():
    if not os.path.exists(SENT_ALERTS_FILE):
        return set()

    try:
        with open(SENT_ALERTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data)
    except Exception as e:
        print(f"⚠️ 無法讀取 sent_alerts.json，將視為沒有已寄紀錄: {e}")
        return set()


def save_sent_alerts(sent_alerts):
    try:
        with open(SENT_ALERTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(sent_alerts)), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 無法寫入 sent_alerts.json: {e}")


def build_alert_key(origin, destination, ticket, user_email):
    depart_date = ticket.get('depart_date', 'unknown')
    return_date = ticket.get('return_date', '單程')
    price = ticket.get('value', 'unknown')
    return f"{origin}-{destination}-{depart_date}-{return_date}-{price}-{user_email}"


# 3. 從環境變數讀取
API_KEY = os.getenv("TRAVELPAYOUTS_API_KEY", "").strip()
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "").strip()
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "").strip()


def validate_environment():
    """檢查必要環境變數，只在直接執行 cron_monitor.py 時呼叫"""
    print("🔐 環境變數檢查：")
    print("🧪 cron_monitor.py 版本: 2026-07-03-affiliate-mvp-v1")
    print(f"TRAVELPAYOUTS_API_KEY 是否存在: {bool(API_KEY)}")
    print(f"TRAVELPAYOUTS_API_KEY 長度: {len(API_KEY) if API_KEY else 0}")
    print(f"SENDER_EMAIL 是否存在: {bool(SENDER_EMAIL)}")
    print(f"SENDER_PASSWORD 是否存在: {bool(SENDER_PASSWORD)}")

    if not API_KEY:
        raise ValueError("❌ 找不到 TRAVELPAYOUTS_API_KEY，請檢查 .env 或 GitHub Secrets。")

    if not SENDER_EMAIL:
        raise ValueError("❌ 找不到 SENDER_EMAIL，請檢查 .env 或 GitHub Secrets。")

    if not SENDER_PASSWORD:
        raise ValueError("❌ 找不到 SENDER_PASSWORD，請檢查 .env 或 GitHub Secrets。")


def generate_search_url(origin, destination, depart_date, return_date=None):
    """產生帶有 Travelpayouts marker 的 Aviasales 搜尋連結，用於 Email CTA"""

    if not depart_date or depart_date == "不限日期":
        depart_date = "2026-12-05"  # 預設安全日期，避免產生無效網址

    if return_date in [None, "", "單程", "不限日期"]:
        return_date = None

    return generate_aviasales_search_url(
        origin=origin,
        destination=destination,
        departure_date=depart_date,
        return_date=return_date,
        adults=1
    )


def send_email_notification(to_email, tickets, target_price):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"✈️ 低價機票提醒：偵測到可能低於 ${target_price} USD 的航班"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 14px; padding: 28px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="font-size: 34px; line-height: 1; margin-bottom: 10px;">✈️</div>
                <h2 style="color: #2563eb; text-align: center; margin: 0; font-size: 24px;">
                    每日低價機票提醒
                </h2>
            </div>

            <p style="font-size: 15px; line-height: 1.7; color: #334155; margin: 0 0 12px 0;">
                您好，我們在每日自動巡檢中，偵測到可能符合您目標價 
                <b>${target_price} USD</b> 的低價機票趨勢。
            </p>

            <p style="font-size: 13px; color: #64748b; line-height: 1.7; margin: 0 0 22px 0;">
                以下價格來自近期票價資料偵測，實際票價、座位與可訂狀態，請點擊按鈕前往 Aviasales 即時頁面確認。
            </p>

            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 22px 0;">
    """

    for idx, ticket in enumerate(tickets):
        return_date_text = ticket.get('return_date', '單程') or '單程'

        html_content += f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; margin-bottom: 18px;">
                
                <div style="margin-bottom: 12px;">
                    <span style="background-color: #dbeafe; color: #1d4ed8; font-size: 12px; font-weight: bold; padding: 5px 10px; border-radius: 999px; display: inline-block;">
                        推薦方案 {idx+1}
                    </span>
                </div>

                <h3 style="margin: 0 0 12px 0; color: #1e293b; font-size: 22px;">
                    {ticket['origin']} → {ticket['destination']}
                </h3>

                <p style="margin: 0 0 16px 0; font-size: 14px; color: #64748b; line-height: 1.8;">
                    📅 去程日期：<b>{ticket['depart_date']}</b><br>
                    📅 回程日期：<b>{return_date_text}</b>
                </p>

                <div style="background-color: #ffffff; border-radius: 10px; padding: 16px; border: 1px solid #e5e7eb;">
                    <p style="font-size: 12px; color: #64748b; margin: 0 0 6px 0; font-weight: bold;">
                        偵測價格
                    </p>

                    <div style="font-size: 30px; font-weight: bold; color: #e11d48; margin-bottom: 16px;">
                        ${ticket['value']} USD
                    </div>

                    <a href="{ticket['search_url']}" target="_blank" 
                       style="background-color: #2563eb; color: #ffffff; text-decoration: none; font-size: 15px; font-weight: bold; padding: 13px 18px; border-radius: 10px; display: block; text-align: center;">
                        查看 Aviasales 即時票價
                    </a>
                </div>
            </div>
        """

    html_content += """
            <div style="margin-top: 24px; padding: 14px; background-color: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0;">
                <p style="font-size: 12px; color: #64748b; line-height: 1.7; margin: 0;">
                    提醒：此價格為系統根據近期票價資料偵測到的低價趨勢，實際票價、稅費、行李規則、座位與可訂狀態，
                    請以點擊後 Aviasales 或航空公司頁面顯示為準。
                </p>
            </div>

            <p style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 22px; line-height: 1.6;">
                此郵件由 AI 機票價格自動監控系統發送。若要取消監控，請至系統頁面刪除任務。
            </p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

def run_auto_monitor():
    if not os.path.exists(MONITOR_FILE):
        print("❌ 沒有偵測到任何監控任務。")
        return

    with open(MONITOR_FILE, 'r', encoding='utf-8') as f:
        try:
            tasks = json.load(f)
        except Exception as e:
            print(f"❌ 任務檔案格式錯誤: {e}")
            return

    print(f"🔄 開始執行自動監控，共 {len(tasks)} 個任務...")
    sent_alerts = load_sent_alerts()
    print(f"📬 已載入 {len(sent_alerts)} 筆已通知紀錄。")


    for task in tasks:
        origin = task['origin']
        destination = task['destination']
        target_price = task['target_price']
        pref_depart = task.get('depart_date')
        pref_return = task.get('return_date')
        user_email = str(task.get('email', '')).strip()

       

        if not user_email or not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", user_email):
            print(f"⚠️ 收件人 Email 格式不正確，跳過此任務: {user_email}")
            continue
        
        print(f"📡 正在向 API 請求 {origin} -> {destination} 的航班資料...")
        
        url = f"https://api.travelpayouts.com/v2/prices/latest?currency=USD&origin={origin}&destination={destination}&token={API_KEY}"
        
        try:
            response = requests.get(url, timeout=10)
            print(f"ℹ️ API 回傳狀態碼: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ API 請求失敗，內容: {response.text}")
                continue
            
            data = response.json().get('data', [])
            print(f"📊 API 回傳了 {len(data)} 筆快取航班資料。")
            
            valid_tickets = []
            for item in data:
                is_depart_match = (pref_depart == "不限日期") or (item.get('depart_date') == pref_depart)
                is_return_match = (pref_return == "單程") or (item.get('return_date') == pref_return)
                
                if is_depart_match and is_return_match:
                    item['search_url'] = generate_search_url(origin, destination, item['depart_date'], item.get('return_date'))
                    valid_tickets.append(item)

            print(f"🎯 符合您指定日期 ({pref_depart}) 的航班有 {len(valid_tickets)} 筆。")

            if valid_tickets:
                sorted_tickets = sorted(valid_tickets, key=lambda x: x['value'])
                lowest_price = sorted_tickets[0]['value']

                print(f"🔍 檢查 {origin}->{destination}: 當前最低價 ${lowest_price} (目標: ${target_price})")

                if lowest_price <= target_price:
                    alert_key = build_alert_key(origin, destination, sorted_tickets[0], user_email)

                    if alert_key in sent_alerts:
                        print(f"🔁 這筆低價通知已寄過，跳過重複通知: {alert_key}")
                    else:
                        print(f"🚨 價格達標！嘗試發送通知信給 {user_email}...")
                        try:
                            send_email_notification(user_email, sorted_tickets[:3], target_price)
                            print(f"✅ Email 發送程序執行完畢！")

                            sent_alerts.add(alert_key)
                            save_sent_alerts(sent_alerts)
                            print(f"📝 已記錄本次通知，避免重複寄送。")
                        except Exception as email_error:
                            print(f"❌ Email 發送失敗: {email_error}")
                else:
                    print(f"⏭️ 最低價 ${lowest_price} 高於目標價 ${target_price}，跳過。")
            else:
                print("⚠️ 找不到符合您指定日期的航班快取資料。")

                
        except Exception as e:
            print(f"❌ 執行任務 {origin}->{destination} 時發生嚴重錯誤: {e}")
            # 印出詳細錯誤行數
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    validate_environment()
    run_auto_monitor()

