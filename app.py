import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from flask import Flask, render_template, request, jsonify

# 1. 引入 dotenv 套件
from dotenv import load_dotenv
# 2. 載入 .env 檔案中的變數
load_dotenv()
# 初始化 Flask
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)

# 3. 從環境變數中讀取設定值
API_KEY = os.getenv("TRAVELPAYOUTS_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
# 任務儲存檔案路徑
MONITOR_FILE = os.path.join(base_dir, 'monitors.json')

def generate_search_url(origin, destination, depart_date, return_date=None):
    """動態生成 Aviasales 搜尋連結"""
    # 格式化日期為 DDMM，例如 2026-12-05 -> 0512
    dep_day = depart_date[8:10]
    dep_month = depart_date[5:7]
    url = f"https://www.aviasales.com/search/{origin}{dep_day}{dep_month}{destination}"
    
    if return_date:
        ret_day = return_date[8:10]
        ret_month = return_date[5:7]
        url += f"{ret_day}{ret_month}"
        
    url += "1" # 1位成人
    return url

def send_email_notification(to_email, tickets, target_price):
    """發送精美 HTML 價格警報郵件"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🚨 價格警報！偵測到低於 ${target_price} USD 的便宜機票！"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    # 建立 HTML 內容
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <h2 style="color: #2563eb; text-align: center; margin-bottom: 20px;">✈️ AI 機票價格監控警報</h2>
            <p>您好，系統偵測到符合您目標價 <b>${target_price} USD</b> 的最優機票組合：</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    """

    for idx, ticket in enumerate(tickets):
        html_content += f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <span style="background-color: #fef3c7; color: #92400e; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">推薦方案 {idx+1}</span>
                <h3 style="margin: 10px 0 5px 0; color: #1e293b;">{ticket['origin']} ➡️ {ticket['destination']}</h3>
                <p style="margin: 5px 0; font-size: 13px; color: #64748b;">
                    📅 去程日期: <b>{ticket['depart_date']}</b><br>
                    📅 回程日期: <b>{ticket.get('return_date', '單程')}</b><br>
                    🔄 轉機次數: <b>{"直飛" if ticket.get('number_of_changes', 0) == 0 else f"轉機 {ticket['number_of_changes']} 次"}</b>
                </p>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 15px;">
                    <span style="font-size: 20px; font-weight: bold; color: #e11d48;">${ticket['value']} USD</span>
                    <a href="{ticket['search_url']}" target="_blank" style="background-color: #10b981; color: white; text-decoration: none; font-size: 12px; font-weight: bold; padding: 8px 16px; border-radius: 6px; display: inline-block;">立即去官網預訂</a>
                </div>
            </div>
        """

    html_content += """
            <p style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 30px;">
                此郵件由 AI 機票價格自動監控系統自動發送。若要取消監控，請至系統後台刪除任務。
            </p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

@app.route('/')
def index():
    # 載入當前所有的監控任務，展示在網頁上
    tasks = []
    if os.path.exists(MONITOR_FILE):
        with open(MONITOR_FILE, 'r', encoding='utf-8') as f:
            try:
                tasks = json.load(f)
            except:
                tasks = []
    return render_template('index.html', tasks=tasks)

@app.route('/check', methods=['POST'])
def check():
    origin = request.form.get('origin').upper().strip()
    destination = request.form.get('destination').upper().strip()
    target_price = float(request.form.get('target_price'))
    pref_depart = request.form.get('depart_date')
    pref_return = request.form.get('return_date')
    email = request.form.get('email', SENDER_EMAIL)

    # 呼叫 API
    url = f"https://api.travelpayouts.com/v2/prices/latest?currency=USD&origin={origin}&destination={destination}&token={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
    except Exception as e:
        return render_template('index.html', status=f"❌ API 連線失敗: {e}", tasks=get_all_tasks())

    if response.status_code != 200:
        return render_template('index.html', status=f"❌ API 請求失敗，錯誤碼: {response.status_code}", tasks=get_all_tasks())

    data = response.json()
    tickets_data = data.get('data', [])

    if not tickets_data:
        backup_url = generate_search_url(origin, destination, pref_depart or "2026-12-05", pref_return)
        status_msg = f"⚠️ 抱歉，API 暫無 {origin} 到 {destination} 的歷史快取資料。但您可以點擊下方連結直接去官網進行即時搜尋！"
        fallback_ticket = [{
            'origin': origin, 'destination': destination, 'value': '???',
            'depart_date': pref_depart or '未指定', 'return_date': pref_return or '單程',
            'gate': 'Aviasales 官網即時搜尋', 'number_of_changes': 0, 'search_url': backup_url
        }]
        return render_template('index.html', status=status_msg, tickets=fallback_ticket, tasks=get_all_tasks())

    valid_tickets = []
    alternative_tickets = []

    for item in tickets_data:
        if 'value' not in item:
            continue
            
        item['search_url'] = generate_search_url(origin, destination, item['depart_date'], item.get('return_date'))
        
        is_depart_match = (not pref_depart) or (item.get('depart_date') == pref_depart)
        is_return_match = (not pref_return) or (item.get('return_date') == pref_return)

        if is_depart_match and is_return_match:
            valid_tickets.append(item)
        else:
            alternative_tickets.append(item)

    # 情況 B：找不到指定日期，推薦其他日期
    if not valid_tickets and alternative_tickets:
        sorted_alt = sorted(alternative_tickets, key=lambda x: x['value'])[:3]
        status_msg = f"ℹ️ 找不到您指定日期 ({pref_depart}) 的快取資料。但我們幫您找到了該航線其他日期的便宜機票！"
        return render_template('index.html', status=status_msg, tickets=sorted_alt, tasks=get_all_tasks())

    # 情況 C：完全沒有符合的資料
    if not valid_tickets:
        backup_url = generate_search_url(origin, destination, pref_depart or "2026-12-05", pref_return)
        status_msg = f"⚠️ 找不到符合的航班資料。建議您直接前往官網進行即時比價。"
        fallback_ticket = [{
            'origin': origin, 'destination': destination, 'value': '???',
            'depart_date': pref_depart or '未指定', 'return_date': pref_return or '單程',
            'gate': 'Aviasales 官網即時搜尋', 'number_of_changes': 0, 'search_url': backup_url
        }]
        return render_template('index.html', status=status_msg, tickets=fallback_ticket, tasks=get_all_tasks())

    # 情況 D：成功找到指定日期的機票
    sorted_tickets = sorted(valid_tickets, key=lambda x: x['value'])
    top_tickets = sorted_tickets[:3]
    lowest_price = top_tickets[0]['value']

    status_msg = f"🎉 成功查詢！目前最低價為 ${lowest_price} USD。"

    if lowest_price < target_price:
        try:
            send_email_notification(email, top_tickets, target_price)
            status_msg += f" 🔴 價格低於目標！已成功發送 Email 通知信至 {email}！"
        except Exception as e:
            status_msg += f" ⚠️ 價格低於目標，但 Email 發送失敗: {e}"
    else:
        status_msg += f" 未低於您的目標價 ${target_price} USD，因此未發送郵件。"

    return render_template('index.html', status=status_msg, tickets=top_tickets, tasks=get_all_tasks())


@app.route('/add_monitor', methods=['POST'])
def add_monitor():
    """新增自動監控任務"""
    origin = request.form.get('origin').upper().strip()
    destination = request.form.get('destination').upper().strip()
    target_price = float(request.form.get('target_price'))
    pref_depart = request.form.get('depart_date') or "不限日期"
    pref_return = request.form.get('return_date') or "單程"
    email = request.form.get('email').strip()

    if not email:
        return render_template('index.html', status="❌ 請輸入有效的 Email 以接收通知！", tasks=get_all_tasks())

    new_task = {
        "origin": origin,
        "destination": destination,
        "target_price": target_price,
        "depart_date": pref_depart,
        "return_date": pref_return,
        "email": email
    }

    tasks = get_all_tasks()

    # 避免重複加入
    if new_task not in tasks:
        tasks.append(new_task)
        with open(MONITOR_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=4)
        status_msg = f"📌 成功將 {origin} ➡️ {destination} (目標價: ${target_price}) 加入每日自動監控清單！"
    else:
        status_msg = "ℹ️ 該監控任務已存在於清單中。"

    return render_template('index.html', status=status_msg, tasks=tasks)


@app.route('/delete_monitor/<int:index>', methods=['POST'])
def delete_monitor(index):
    """刪除指定的監控任務"""
    tasks = get_all_tasks()
    if 0 <= index < len(tasks):
        removed = tasks.pop(index)
        with open(MONITOR_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=4)
        status_msg = f"🗑️ 已成功刪除 {removed['origin']} ➡️ {removed['destination']} 的監控任務。"
    else:
        status_msg = "❌ 找不到該監控任務。"
    
    return render_template('index.html', status=status_msg, tasks=tasks)


def get_all_tasks():
    """輔助函式：取得所有任務"""
    if os.path.exists(MONITOR_FILE):
        with open(MONITOR_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
