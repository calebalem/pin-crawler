import json
import sqlite3
import sys
import threading
import time
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service as chrome_service
from selenium.webdriver.chrome.options import Options as chrome_options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver
import time
import re
import os
import undetected_chromedriver as uc
from concurrent.futures import ThreadPoolExecutor
from sel import Sel
from progress.bar import ChargingBar


# creating output folder.
out_folder = 'outputs'
os.makedirs(out_folder, exist_ok=True)

file_out_path = os.path.join(out_folder, 'output_of_second_tool.json')
Separator_for_csv = "\t"
DATABASE_PATH = "database.db"
HOW_MANY_WINDOWS_DO_YOU_NEED = 1
total_pins = 0



def page_has_loaded(driver, sleep_time = 1):
    '''
    Waits for page to completely load by comparing current page hash values.
    '''

    def get_page_hash(driver):
        '''
        Returns html dom hash
        '''
        # can find element by either 'html' tag or by the html 'root' id
        dom = driver.find_element(By.TAG_NAME,'html').get_attribute('innerHTML')
        # dom = driver.find_element_by_id('root').get_attribute('innerHTML')
        dom_hash = hash(dom.encode('utf-8'))
        return dom_hash

    page_hash = 'empty'
    page_hash_new = ''
    
    # comparing old and new page DOM hash together to verify the page is fully loaded
    while page_hash != page_hash_new: 
        page_hash = get_page_hash(driver)
        time.sleep(sleep_time)
        page_hash_new = get_page_hash(driver)
        print('<page_has_loaded> - page not loaded')

    print('<page_has_loaded> - page not loaded')

class window:
    all_links = {}
    count_load_failt = 0
    temp_length = -1
    count = 0
    board_url= None
    ending_count = 0
    pin_count = 0
    def __init__(self,progress_bar,board_url,args):
        self.progress_bar = progress_bar
        self.args = args
        self.retries = 2
        self.board_url = board_url
        sel = Sel(self.args)
        self.driver = sel.get_driver()

    def start(self):
        self.load_board_page()
        self.get_link_pin()

    def load_board_page(self):
        self.all_links = {}
        self.driver.set_page_load_timeout(3000)
        try:
            self.driver.get(self.board_url)
            self.driver.execute_script("document.body.style.zoom='50%'")
            pin_count_element = self.driver.find_element(By.XPATH,"/html[1]/body[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[3]/div[1]/div[2]/div[1]/span[1]/span[1]/div[1]/div[1]")
            p_t = pin_count_element.text.split(" ")[0].replace(",","")
            self.pin_count = int(p_t)
            self.count_load_failt = 0
        except Exception as e:
            print(e)
            self.count_load_failt += 1
            if(self.count_load_failt == 4):
                return
            else:
                self.start()

       
        
    def get_link_pin(self):
        try:
            main_content = self.driver.find_element(By.XPATH,"/html[1]/body[1]/div[1]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[5]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/div[1]/div[1]/div[1]")
            links = main_content.find_elements(By.TAG_NAME,"a")
            pin_links = []
            last_link = ""
            self.progress_bar.bar_prefix = f"Scraping {self.board_url}"
            self.progress_bar.update()
            while len(pin_links) < self.pin_count:
                for link in links:
                    href = link.get_attribute("href")
                    last_link = link
                    if href.startswith("https://www.pinterest.com/pin/"):
                        if href not in pin_links:
                            pin_links.append(href)
                            self.all_links[href.replace("https://www.pinterest.com","")] = None
                self.driver.execute_script("arguments[0].scrollIntoView(true);",last_link)
                #sleep for two sec after scrolling the last link to viewport to prevent stale element reference
                time.sleep(2)
                links = main_content.find_elements(By.TAG_NAME,"a")
            self.push_pin_links_to_database(pin_links)
            global total_pins
            total_pins += len(pin_links)
            set_board_is_scraped(self.board_url)
            self.progress_bar.bar_prefix = f"Finished scraping {self.board_url} "
            self.progress_bar.next()
            self.driver.close()
            self.driver.quit()
        except Exception as e:
            print(e)
            if (self.retries):
                print(f"\nEncountered error scraping {self.board_url}")
                print("Retrying in 2 seconds...")
                time.sleep(2)
                self.start()
                self.retries -= 1
                return
            else:
                print(f"\nSkipping board {self.board_url} due to error.")
                self.driver.close()
                self.driver.quit()
                return
            
    def push_pin_links_to_database(self, pin_urls):
        cmd = 'INSERT INTO stage2(board_url, pin_url) values'
        try:
            with sqlite3.connect(DATABASE_PATH) as conn:
                for i in range(len(pin_urls)):
                    if i != len(pin_urls) - 1:
                        cmd += "('" + \
                        str(self.board_url)+"','"+str(pin_urls[i])+"'),"
                    else:
                        cmd += "('" + \
                        str(self.board_url)+"','"+str(pin_urls[i])+"');"
                conn.execute(cmd)
                conn.commit()
        except Exception as e:
                    print(e)
                    time.sleep(1)
                    self.push_to_database(pin_urls)

def push_total_image_count():
    cmd = f"insert into report(total_images) values ({total_pins})"
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.execute(cmd)
            conn.commit()
    except Exception as e:
        print(e)
        time.sleep(1)
        push_total_image_count()

def process(board_list,progress_bar,args):
    with ThreadPoolExecutor(max_workers=args["max_pin_threads"]) as executor:
        for i in range(len(board_list)):
            board_url = board_list[i]
            win = window(progress_bar,board_url,args)
            executor.submit(win.start)
    push_total_image_count()
    print(f"\nTotal Pins: {total_pins}")

def output_json_file():
    json_data = []
    data = {}
    number_of_images = {}
    cmd = "select board_url, pin_url from stage2"
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.execute(cmd)
        conn.commit()
    cursor_temp = []
    for i in cursor:
        cursor_temp.append(i)
    cmd = "select board_url, pin_url, count(pin_url) from stage2 group by board_url"
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor_for_pins = conn.execute(cmd)
        conn.commit()
    for cur in cursor_for_pins:
        number_of_images[cur[0]] = cur[2]
    for cur in cursor_temp:
        data[cur[0]] = None
    
    count = 0
    for board_url in data:
        count+=1
        pins = []
        for cur in cursor_temp:
            if(cur[0] == board_url):
                pins.append(cur[1])
        # print({"board url": board_url, "number of images": number_of_images[board_url], "pins": pins})
        json_data.append({"board url": board_url, "number of images": number_of_images[board_url], "pins": pins})
    json_data = {get_search_term():json_data}
    json_string = json.dumps(json_data)

    with open(file_out_path, 'w') as outfile:
        outfile.write(json_string)

def get_board_urls():
    returns = []
    cmd = "select board_url from stage1"
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.execute(cmd)
            conn.commit()
            for i in cursor:
                returns.append(i[0])
    except:
        time.sleep(1)
        return get_board_urls()
    return returns

def get_search_term():
    cmd = "select search_term from stage1 LIMIT 1;"
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.execute(cmd)
            conn.commit()
            for i in cursor:
                return i[0]
    except:
        time.sleep(1)
        return get_search_term()

def set_board_is_scraped(url):
    cmd = "update stage1 set scraped = 1 where board_url = '"+url+"';"
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.execute(cmd)
            conn.commit()
    except Exception as e:
        print(str(e))
        time.sleep(1)
        return set_board_is_scraped(url)
    
class Stage2: 
    def __init__(self,args) -> None:
        self.args = args
    
    def run(self) -> None:
        print("\n\nStarted scraping boards for pin urls....") 
        """
            function that executes the second stage of Pintrest scraping, which is retrieveing the board urls which was collected 
            in stage 1 and goes in them 1 by one to collect all pens urls within those boards and storing the pin urls inside the sqlite DB. 
        """
        
        board_urls = get_board_urls()
        progress_bar = ChargingBar('',max=len(board_urls),suffix='%(percent)d%% - %(index)d/%(max)d')
        process(board_urls,progress_bar,self.args)
        output_json_file()
        print("Finished scraping pin urls")
        return 

if __name__ == '__main__':
    try:
        for i in range(len(sys.argv)):
            if(sys.argv[i] == '-o'):
                file_out_path = sys.argv[i+1]
                break
    except:
        print("file_out_path is not set yet!")

    board_urls = get_board_urls()
    
    process(board_urls)

    output_json_file()
    