import os
import smtplib
import requests
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.header import Header

load_dotenv()

API_KEY = os.getenv('API_KEY')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')


def generate_search_url(origin, destination, depart_date, return_date=None):
    """
    根據航線與日期，自動產生 Aviasales (Travelpayouts) 的搜尋連結。
    格式: https://www.aviasales.com/search/BKK2009TPE1
    去程日期格式: DDMM (例如 20 Sep 2026 -> 2009)
    """
    try:
        # 解析去程日期 (YYYY-MM-DD -> DDMM)
        dep_parts = depart_date.split('-')
        dep_str = f"{dep_parts[2]}{dep_parts[1]}"
        
        if return_date:
            # 解析回程日期 (YYYY-MM-DD -> DDMM)
            ret_parts = return_date.split('-')
            ret_str = f"{ret_parts[2]}{ret_parts[1]}"
            # 來回票連結格式: BKK2009TPE27091 (最後的 1 代表 1 位成人)
            url = f"https://www.aviasales.com/search/{origin}{dep_str}{destination}{ret_str}1"
        else:
            # 單程票連結格式
            url = f"https://www.aviasales.com/search/{origin}{dep_str}{destination}1"
        return url
    except Exception:
        # 若解析失敗，提供預設搜尋首頁
        return "https://www.aviasales.com"


def check_ticket_price(route, target_price):
    """
    檢查指定航線的機票價格，篩選出低於目標價格的前 3 筆最便宜機票（包含不同去回程日期）。
    """
    origin, destination = route.split('-')
    # 使用 latest API 獲取近期所有搜尋到的價格
    url = f"https://api.travelpayouts.com/v2/prices/latest?currency=USD&origin={origin}&destination={destination}&token={API_KEY}"
    response = requests.get(url, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        print(f"API 回傳原始資料筆數: {len(data.get('data', []))} 筆")

        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            # 1. 篩選出有價格、且低於目標價格的機票
            valid_tickets = [item for item in data['data'] if 'value' in item and item['value'] < target_price]
            
            if valid_tickets:
                # 2. 依照價格由低到高排序
                sorted_tickets = sorted(valid_tickets, key=lambda x: x['value'])
                
                # 3. 取出前 3 筆最便宜的機票（可能包含不同去回程日期）
                top_tickets = sorted_tickets[:3]
                
                print(f"發現 {len(top_tickets)} 筆低於目標價 ${target_price} USD 的機票！準備發送詳細郵件...")
                send_email_notification(top_tickets, target_price)
            else:
                print(f"目前沒有任何機票價格低於目標價 ${target_price} USD。")
        else:
            print("找不到任何價格資料（data 欄位為空）。")
    else:
        print(f"Error fetching data: {response.status_code}")


def send_email_notification(tickets, target_price):
    """
    發送包含多個航班資訊與購票連結的 HTML 郵件。
    """
    # 取得第一筆機票的航線資訊作為標題使用
    first_ticket = tickets[0]
    origin = first_ticket.get('origin', 'N/A')
    destination = first_ticket.get('destination', 'N/A')
    lowest_price = first_ticket.get('value', 'N/A')

    # 動態生成多個航班的 HTML 表格列
    table_rows = ""
    for idx, ticket in enumerate(tickets, 1):
        price = ticket.get('value', 'N/A')
        dep_date = ticket.get('depart_date', 'N/A')
        ret_date = ticket.get('return_date', '單程')
        gate = ticket.get('gate', 'N/A')
        changes = ticket.get('number_of_changes', 0)
        duration_mins = ticket.get('duration', 0)
        
        # 格式化飛行時間與轉機
        duration_str = f"{duration_mins // 60}h {duration_mins % 60}m" if duration_mins else "未知"
        changes_str = "直飛" if changes == 0 else f"轉機 {changes} 次"
        
        # 產生搜尋/購票連結
        search_url = generate_search_url(origin, destination, dep_date, ticket.get('return_date'))

        # 醒目標示最便宜的第一名
        row_style = "background-color: #fff9e6; font-weight: bold;" if idx == 1 else ""
        badge = "<span style='background-color: #ffc107; color: black; padding: 2px 6px; border-radius: 4px; font-size: 11px;'>首選最低價</span>" if idx == 1 else f"選擇 {idx}"

        table_rows += f"""
        <tr style="{row_style}">
            <td style="padding: 12px; border-bottom: 1px solid #ddd; text-align: center;">{badge}</td>
            <td style="padding: 12px; border-bottom: 1px solid #ddd; color: #d9534f; font-size: 16px; font-weight: bold;">${price} USD</td>
            <td style="padding: 12px; border-bottom: 1px solid #ddd;">
                去：{dep_date}<br>
                <span style="color: #666; font-size: 12px;">回：{ret_date}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #ddd; font-size: 13px;">
                {changes_str}<br>
                <span style="color: #666; font-size: 11px;">歷時: {duration_str}</span>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #ddd; text-align: center;">
                <a href="{search_url}" target="_blank" style="background-color: #28a745; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 13px; font-weight: bold; display: inline-block;">立即搜尋 ➔</a>
                <br><span style="color: #888; font-size: 10px; display: block; margin-top: 4px;">平台: {gate}</span>
            </td>
        </tr>
        """

    # 組合完整 HTML 郵件內容
    email_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 650px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 20px; border-radius: 10px; background-color: #ffffff; }}
            .header {{ background-color: #007bff; color: white; padding: 15px; border-radius: 8px 8px 0 0; font-size: 20px; font-weight: bold; text-align: center; }}
            .sub-title {{ margin-top: 15px; font-size: 15px; color: #555; }}
            .ticket-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .ticket-table th {{ background-color: #f8f9fa; color: #333; padding: 12px; text-align: left; font-weight: bold; border-bottom: 2px solid #dee2e6; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">✈️ 降價通知：發現多個便宜航班組合！</div>
            <p class="sub-title">您監控的航線 <strong>{origin} ➡️ {destination}</strong>（目標價：${target_price} USD）已成功偵測到降價。以下為我們為您篩選出的 <strong>Top 3 最划算日期組合</strong>：</p>
            
            <table class="ticket-table">
                <thead>
                    <tr>
                        <th style="width: 15%; text-align: center;">排行</th>
                        <th style="width: 18%;">價格</th>
                        <th style="width: 27%;">出發 / 回程日期</th>
                        <th style="width: 20%;">航班資訊</th>
                        <th style="width: 20%; text-align: center;">購票連結</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            
            <p style="margin-top: 25px; font-size: 13px; color: #666; background-color: #f1f3f5; padding: 10px; border-radius: 5px;">
                💡 <strong>提示：</strong> 點擊右側的「<strong>立即搜尋 ➔</strong>」按鈕，系統會自動帶入對應的去回程日期，幫您直接跳轉至 Aviasales 搜尋頁面進行比價與訂購。
            </p>
            
            <div class="footer">
                此信件由您的專屬 AI 機票監控 SaaS 系統自動發送。<br>
                若要調整監控目標，請修改腳本設定。
            </div>
        </div>
    </body>
    </html>
    """

    # 建立郵件
    msg = MIMEText(email_content, 'html', 'utf-8')
    msg['Subject'] = Header(f"🔥 機票降價！{origin} ➡️ {destination} 最低只要 ${lowest_price} USD！", 'utf-8')
    msg['From'] = '912yan@gmail.com'
    msg['To'] = '912yan@gmail.com'

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls() 
            server.login('912yan@gmail.com', EMAIL_PASSWORD)
            server.send_message(msg)
            print("🎉 成功發送包含多個航班與購票網址的詳細通知郵件！")
    except Exception as e:
        print(f"❌ 郵件發送失敗: {e}")


# 測試執行
if __name__ == "__main__":
    # 監控 BKK-TPE，目標價 300 USD
    check_ticket_price("BKK-TPE", 200)
