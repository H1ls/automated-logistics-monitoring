import re
import os
import time
import json
import pickle
import gspread
import logging
from typing import Any
from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.common import TimeoutException
from selenium.webdriver.common.keys import Keys
from google.oauth2.service_account import Credentials
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import math

from selenium.webdriver.chrome.service import Service