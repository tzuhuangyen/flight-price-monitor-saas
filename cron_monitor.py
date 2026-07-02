# cron_monitor.py
import os
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import traceback
import requests


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


print("🔐 環境變數檢查：")
print("🧪 cron_monitor.py 版本: 2026-07-02-fix-threshold-v2")
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
    if not depart_date or depart_date == "不限日期":
        depart_date = "2026-12-05" # 預設安全日期
    dep_day = depart_date[8:10]
    dep_month = depart_date[5:7]
    url = f"https://www.aviasales.com/search/{origin}{dep_day}{dep_month}{destination}"
    if return_date and return_date != "單程":
        ret_day = return_date[8:10]
        ret_month = return_date[5:7]
        url += f"{ret_day}{ret_month}"
    url += "1"
    return url

def send_email_notification(to_email, tickets, target_price):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🚨 [自動監控] 發現低於 ${target_price} USD 的便宜機票！"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <h2 style="color: #2563eb; text-align: center; margin-bottom: 20px;">✈️ 每日自動監控警報</h2>
            <p>您好，系統在每日自動巡檢中，偵測到符合您目標價 <b>${target_price} USD</b> 的機票：</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    """

    for idx, ticket in enumerate(tickets):
        html_content += f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <span style="background-color: #fef3c7; color: #92400e; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">推薦方案 {idx+1}</span>
                <h3 style="margin: 10px 0 5px 0; color: #1e293b;">{ticket['origin']} ➡️ {ticket['destination']}</h3>
                <p style="margin: 5px 0; font-size: 13px; color: #64748b;">
                    📅 去程日期: <b>{ticket['depart_date']}</b><br>
                    📅 回程日期: <b>{ticket.get('return_date', '單程')}</b>
                </p>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 15px;">
                    <span style="font-size: 20px; font-weight: bold; color: #e11d48;">${ticket['value']} USD</span>
                    <a href="{ticket['search_url']}" target="_blank" style="background-color: #10b981; color: white; text-decoration: none; font-size: 12px; font-weight: bold; padding: 8px 16px; border-radius: 6px; display: inline-block;">立即去官網預訂</a>
                </div>
            </div>
        """

    html_content += """
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
    run_auto_monitor()
