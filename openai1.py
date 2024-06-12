import speech_recognition as sr
import requests
import pygame
import edge_tts
import asyncio
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from datetime import datetime, timedelta
import traceback
from openai import OpenAI
import time

def recognize_speech_from_microphone():  #語音辨識
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("請說點什麼...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)
        
        try:
            text = recognizer.recognize_google(audio, language="zh-TW")
            print("你說了: " + text)
            return text
        except sr.UnknownValueError:
            print("Google 語音識別無法理解音頻")
            return None
        except sr.RequestError as e:
            print("無法從 Google 語音識別服務請求結果; {0}".format(e))
            return None

def get_news(api_key):  #連接新聞api並回傳新聞json
    url = f"https://gnews.io/api/v4/top-headlines?&category=general&country=tw&max=10&apikey={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        print(response.json())
        return response.json()['articles']
    else:
        print("Failed to retrieve news")
        return None
        
async def text_to_speech(text):  #將文字轉成mp3檔
    communicate = edge_tts.Communicate(text, "zh-TW-YunJheNeural")
    filename = "output.mp3"
    await communicate.save(filename)
    play_audio(filename)

def play_audio(filename):  #播放mp3
    pygame.mixer.init()
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.quit()    

def get_weather(latitude, longitude):  #連接中央氣象局天氣api並回傳天氣格式
    url = "https://opendata.cwa.gov.tw/linked/graphql"
    authorization = ""  #這裡要放中央氣象局的憑證
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    query = '''
    query town($longitude: Float!, $latitude: Float!) {
      town (longitude: $longitude, latitude: $latitude) {
        ctyCode,
        ctyName,
        townCode,
        townName,
        villageCode,
        villageName,
        forecast72hr {
          locationName,
          locationID,
          latitude,
          longitude,
          AT {
            description,
            timePeriods {
              dataTime,
              apparentTemperature,
              measures
            }
          },
          CI {
            description,
            timePeriods {
              dataTime,
              comfortIndex,
              measures
            }
          },
          PoP6h {
            description,
            timePeriods {
              startTime,
              endTime,
              probabilityOfPrecipitation,
              measures
            }
          },
          T {
            timePeriods {
              dataTime,
              temperature,
              measures
            }
          },
          WeatherDescription {
            description
            timePeriods {
              startTime,
              endTime,
              weatherDescription,
              measures
            }
          },
          Wx {
            description,
            timePeriods {
              startTime,
              endTime,
              weather,
              weatherIcon,
              measures
            }
          }
        },
        forecastWeekday {
          locationName,
          locationID,
          latitude,
          longitude,
          PoP12h {
            description,
            timePeriods {
              startTime,
              endTime,
              probabilityOfPrecipitation,
              measures
            }
          },
          T {
            description,
            timePeriods {
              startTime,
              endTime,
              temperature,
              measures
            }
          },
          MinT {
            description,
            timePeriods {
              startTime,
              endTime,
              temperature,
              measures
            }
          },
          MaxT {
            description,
            timePeriods {
              startTime,
              endTime,
              temperature,
              measures
            }
          },
          UVI {
            description,
            timePeriods {
              startTime,
              endTime,
              UVIndex,
              UVIDescription,
              measures
            }
          },
          WeatherDescription {
            description
            timePeriods {
              startTime,
              endTime,
              weatherDescription,
              measures
            }
          },
          Wx {
            description,
            timePeriods {
              startTime,
              endTime,
              weather,
              weatherIcon,
              measures
            }
          }
        }
      }
    }
    '''
    variables = {"longitude": float(longitude), "latitude": float(latitude)}
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to get weather data.")
        return None

def find_closest_time(data):  #找最接近現在的天氣預報時間
    now = datetime.now()
    closest_time = min(data, key=lambda x: abs(now - datetime.fromisoformat(x['dataTime'])))
    return datetime.fromisoformat(closest_time['dataTime'])

def get_closest_forecast(weather_data, current_time):  #獲取最接近現在的天氣預報時間之資料
    # 初始化最接近当前时间的预报数据
    closest_at = None
    closest_WeatherDescription = None
    min_time_difference = float('inf')  # 初始设为无穷大

    # 提取最接近当前时间的预报数据
    for period in weather_data['data']['town']['forecast72hr']['AT']['timePeriods']:
        forecast_time = datetime.fromisoformat(period["dataTime"])
        time_difference = abs((current_time - forecast_time).total_seconds())
        if time_difference < min_time_difference:
            min_time_difference = time_difference
            closest_at = period["apparentTemperature"]

    for period in weather_data['data']['town']['forecast72hr']['WeatherDescription']['timePeriods']:
        start_time = datetime.fromisoformat(period["startTime"])
        end_time = datetime.fromisoformat(period["endTime"])
        if start_time <= current_time <= end_time:
            closest_WeatherDescription = period["weatherDescription"]
            break

    return closest_at, closest_WeatherDescription

def get_openai(user_command):  #連接openai api並請他判斷使用者回答
    client = OpenAI(
    api_key=(""),  #這裡要放openai之api key
)

    response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "區分接下來的句子是有關新聞還是天氣，回答我是哪一個就好，不需要其他資訊，如果只有新聞就輸出新聞。"},
        {"role": "user", "content": user_command}
    ]
    
    )

    assistant_reply = response.choices[0].message.content
    print(response.choices[0].message.content)
    return assistant_reply

def openai_in_news(news_summary,user_command_news):  #連接openai api並請他判斷使用者欲知道的新聞摘要
    client = OpenAI(
    api_key=(""),  #這裡要放openai之api key
)

    response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": f"你負責判斷: {news_summary}中,比對使用者想聽的是第幾則新聞的摘要,如果使用者說出title中的關鍵字,回覆我該新聞的index,例如第一則回覆我數字0,以此類推,只能回覆我數字,不需要其他字"},
        {"role": "user", "content": user_command_news}
    ]
    
    )

    assistant_reply = response.choices[0].message.content
    print(response.choices[0].message.content)
    return assistant_reply

def openai_in_weather(closest_WeatherDescription):  #連接openai api給予該天氣狀況下的建議
    client = OpenAI(
    api_key=(""),  #這裡要放openai之api key
)

    response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": f"你負責判斷: {closest_WeatherDescription},建議使用者該攜帶哪些東西出門或是該注意什麼"}
    ]
    
    )

    assistant_reply = response.choices[0].message.content
    print(response.choices[0].message.content)
    return assistant_reply

def main():
    # 步驟1：語音識別
    user_command = recognize_speech_from_microphone()
        
    if user_command:
        openai_response = get_openai(user_command)
        user_command = user_command.lower()
        if "新聞" in openai_response:
            # 使用你的 API 密鑰
            api_key = '' #新聞api   #這裡要放Gnews之api key
            # 步驟2：新聞抓取
            articles = get_news(api_key)
            
            if articles:
                summaries = []
                for i,article in enumerate (articles[:5],1):  # 只處理前5條新聞
                    summary = f"這是第{i}則新聞:{article['title']}"
                    summaries.append(summary)
                
                # 步驟4：語音合成
                news_summary = " ".join(summaries)
                asyncio.run(text_to_speech(news_summary))
                time.sleep(5)
                user_command_news = recognize_speech_from_microphone()
                openai_news_response = openai_in_news(news_summary,user_command_news)
                openai_news_response = int(openai_news_response)
                asyncio.run(text_to_speech(articles[openai_news_response]['description']))               
            else:
                print("未找到新聞")
                asyncio.run(text_to_speech("未找到新聞"))
        elif "天氣" in openai_response:
                                # 啟動 Chrome 瀏覽器
            driver = webdriver.Chrome()

            # 打開 HTML 文件
            driver.get("C:/Users/user/OneDrive - mail.nuk.edu.tw/桌面/Dlib/geolocation.html")

            try:
                # 等待出現提示框
                prompt = WebDriverWait(driver, 10).until(
                    EC.alert_is_present()
                )

                # 如果提示框出現，點擊「允許」按鈕
                prompt.accept()
                print("已按下「允許」按鈕")
            except:
                print("沒有出現位置存取提示框")

            try:
                # 等待地理位置信息出現
                location_tag = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "location"))
                )

                # 解析 HTML 文件，獲取地理位置信息
                location_info = location_tag.text.strip()
                
                # 提取經度和緯度
                match = re.search(r"緯度：([\d.]+), 經度：([\d.]+)", location_info)
                if match:
                    latitude = match.group(1)
                    longitude = match.group(2)
                    
                    # 查詢天氣資訊
                    weather_data = get_weather(latitude, longitude)
                    city_name = weather_data['data']['town']['ctyName']
                    town_name = weather_data['data']['town']['townName']
                    villageName = weather_data['data']['town']['villageName']
                    a = weather_data['data']['town']['forecast72hr']['AT']['timePeriods'] #a只有AT溫度
                    closest_time = find_closest_time(a)
                    current_time = datetime.now()
                    closest_at, closest_WeatherDescription = get_closest_forecast(weather_data, current_time)
                    Wmessage0 = f"為您報告: {city_name} {town_name} {villageName} {str(closest_time)} 的氣象預報。體感溫度為: {closest_at} 度。{closest_WeatherDescription}"
                    asyncio.run(text_to_speech(Wmessage0))
                    print("體感溫度為:",closest_at,"度")
                    print(closest_WeatherDescription)
                    ai_response_in_weather=openai_in_weather(closest_WeatherDescription)
                    asyncio.run(text_to_speech(ai_response_in_weather))
                    print(ai_response_in_weather)

                    
                    
            except Exception as e:
                    traceback.print_exc()
                    print(f"出現錯誤: {e}")

            # 關閉瀏覽器
            driver.quit()
               
        else:
            print("未識別有效命令")
            asyncio.run(text_to_speech("未識別有效命令"))   
    else:
        print("未識別任何命令")
        asyncio.run(text_to_speech("未識別任何命令"))

if __name__ == "__main__":
    main()
