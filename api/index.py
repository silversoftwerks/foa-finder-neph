#!/Users/emuckley/Documents/Github/foa-finder/webenv/bin/python

# -*- coding: utf-8 -*-


"""

What this script does:
(1) finds the latest FOA database on grants.gov
(2) downloads the database
(3) unzips the database to an xml file
(4) converts the xml database into a pandas dataframe
(5) filters the FOA dataframe by keywords
(6) sends the filtered FOA list to a dedicated channel on Slack.

python version to use for crontab scheduling in virtual environment:
Users/emuckley/Documents/GitHub/foa-finder/webenv/bin/python


crontab script to run every 24 hours at 18:05 hrs:
5 18 * * * /Users/emuckley/Documents/GitHub/foa-finder/app.py >> ~/cron.log 2>&1


"""
# %%%%%%%%%%%%%%%%%%%% find the database %%%%%%%%%%%%%%%%%%%%%%%%%%


import os
import io
import json
import time
import zipfile
import requests
import pandas as pd
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from flask import Flask, request, g


pd.options.mode.chained_assignment = None
app = Flask(__name__)


def get_xml_url_and_filename():
    """Get the URL and filename of the most recent XML database file
    posted on grants.gov."""

    day_to_try = datetime.today()

    file_found = None
    while file_found is None:
        url = 'https://www.grants.gov/extract/GrantsDBExtract{}v2.zip'.format(
            day_to_try.strftime('%Y%m%d'))
        print(url)
        response = requests.get(url, stream=True, allow_redirects=True, timeout=1
                                )
        total_size_in_bytes = int(response.headers.get('content-length', 0))

        print('response', total_size_in_bytes)

        # look back in time if todays data is not posted yet
        if response.status_code == 200:
            file_found = url
        else:
            day_to_try = day_to_try - timedelta(days=1)

        filename = 'GrantsDBExtract{}v2.zip'.format(
            day_to_try.strftime('%Y%m%d'))

    print('Found database file {}'.format(filename))

    return url, filename


# %%%%%%%%%%%%%%%%%%%% download the database %%%%%%%%%%%%%%%%%%%%%%%%%%


def download_file_from_url(url, filename):
    """Download a file from a URL"""
    # remove all previously-downloaded zip files
    [os.remove(f) for f in os.listdir() if f.endswith(".zip")]
    # ping the dataset url
    response = requests.get(url, stream=True, timeout=5)
    # print('response', response)

    # if file url is found
    if response.status_code == 200:
        print('downloading')
        handle = open(filename, "wb")
        for chunk in response.iter_content(chunk_size=512):
            if chunk:  # filter out keep-alive new chunks
                handle.write(chunk)
        handle.close()
        time.sleep(3)
        print('Database successfully downloaded')
    # if file url is not found
    else:
        print('URL does not exist')


def unzip(filename):
    """Unzip a zip file and parse it using beautiful soup"""

    xml = None
    # unzip raw file
    with zipfile.ZipFile(filename, "r") as z:
        xml = io.BytesIO(z.read(filename.replace('.zip', '.xml')))

    return xml


def soupify(xml):
    # parse as tree and convert to string
    tree = ET.parse(xml)
    root = tree.getroot()
    doc = str(ET.tostring(root, encoding='unicode', method='xml'))
    # initialize beautiful soup object
    soup = BeautifulSoup(doc, 'lxml')
    print('Database unzipped')
    return soup


day_to_try = datetime.today()
zipped_filepath = 'GrantsDBExtract{}v2.zip'.format(
    day_to_try.strftime('%Y%m%d'))
try:
    file_found = open(zipped_filepath, 'r')
    print('file found')
except Exception as error:
    file_found = None
if (file_found == None):
    print('file not found')
    # get url and filename of the latest database available for extraction
    url, filename = get_xml_url_and_filename()
    print(url, filename)
    # download the database zip file
    download_file_from_url(url, filename)
    # get beautiful soup object from parsed zip file
    zipped_filepath = filename

xml = unzip(zipped_filepath)
soup = soupify(xml)

# %%%%%%%%%%%%%%%%%%%%%%%%% unzip and parse file %%%%%%%%%%%%%%%%%%%%%


# %%%%%%%%%%%% populate dataframe with every xml tag %%%%%%%%%%%%%%%%%%%%


def soup_to_df(soup):
    """Convert beautifulsoup object from grants.gov XML into dataframe"""
    # list of bs4 FOA objects
    s = 'opportunitysynopsisdetail'
    foa_objs = [tag for tag in soup.find_all() if s in tag.name.lower()]

    # loop over each FOA in the database and save its details as a dictionary
    dic = {}
    for i, foa in enumerate(foa_objs):
        ch = foa.findChildren()
        dic[i] = {fd.name.split('ns0:')[1]: fd.text for fd in ch}

    # create dataframe from dictionary
    df = pd.DataFrame.from_dict(dic, orient='index')
    return df


# get full dataframe of all FOAs
dff = soup_to_df(soup)


# %%%%%%%%%%%%%%%%%% filter by dates and keywords %%%%%%%%%%%%%%%%%%%%%%%%

def to_date(date_str):
    """Convert date string from database into date object"""
    return datetime.strptime(date_str, '%m%d%Y').date()


def is_recent(date, days=14):
    """Check if date occured within n amount of days from today"""
    return (datetime.today().date() - to_date(date)).days <= days


def is_open(date):
    """Check if FOA is still open (closedate is in the past)"""
    if type(date) == float:
        return True
    elif type(date) == str:
        return (datetime.today().date() - to_date(date)).days <= 0


def reformat_date(s):
    """Reformat the date string with hyphens so its easier to read"""
    s = str(s)
    return s[4:]+'-'+s[:2]+'-'+s[2:4]


def sort_by_recent_updates(df):
    """Sort the dataframe by recently updated dates"""
    new_dates = [reformat_date(i) for i in df['lastupdateddate']]
    df.insert(1, 'updatedate', new_dates)
    df = df.sort_values(by=['updatedate'], ascending=False)
    print('Databae sorted and filtered by date')
    return df


def filter_by_keywords(df, filter):
    """Filter the dataframe by keywords and nonkeywords (words to avoid).
    The keywords and nonkeywords are set in external csv files called
    'keywords.csv' and 'nonkeywords.csv'"""
    # get keywords to filter dataframe
    keywords = filter.split(',')
    keywords_str = '|'.join(keywords).lower()
    # get non-keywords to avoid

    # filter by post date - the current year and previous year only
    # curr_yr = np.max([int(i[-4:]) for i in df['postdate'].values])
    # prev_yr = curr_yr - 1
    # df = df[df['postdate'].str.contains('-'+str(curr_yr), na=False)]

    # filter dataframe by keywords and nonkeywords
    df = df[df['description'].str.contains(keywords_str, na=False)]

    print('Database filtered by keywords')

    return df


# include only recently updated FOAs
df = dff[[is_recent(i) for i in dff['lastupdateddate']]]

# include only FOAs which are not closed
df = df[[is_open(i) for i in df['closedate']]]

# sort by newest FOAs at the top
df = sort_by_recent_updates(df)


# %%%%%%%%%%%%%%% format string message for Slack %%%%%%%%%%%%%%%%%%%%%%


def create_slack_text(filename, df, print_text=True):
    """Create text to send into Slack"""
    # get database date
    db_date = filename.split('GrantsDBExtract')[1].split('v2')[0]
    db_date = db_date[:4]+'-'+db_date[4:6]+'-'+db_date[6:]

    # create text
    slack_text = 'Showing {} recently updated FOAs from grants.gov, extracted {}:'.format(
        len(df), db_date)
    slack_text += '\n======================================='

    base_hyperlink = r'https://www.grants.gov/web/grants/search-grants.html?keywords='

    # loop over each FOA title and add to text
    for i in range(len(df)):

        hyperlink = base_hyperlink + df['opportunitynumber'].iloc[i]

        slack_text += '\n{}) Updated: {},  Closes: {}, Title: {}, {} ({}) \n{}'.format(
            i+1,
            df['updatedate'].iloc[i],
            reformat_date(df['closedate'].iloc[i]),
            df['opportunitytitle'].iloc[i].upper(),
            df['opportunitynumber'].iloc[i],
            df['opportunityid'].iloc[i],
            hyperlink)
        slack_text += '\n----------------------------------'

    slack_text += '\nFOAs filtered by date and keywords in {}'.format(
        'https://github.com/ericmuckley/foa-finder/blob/master/keywords.csv.')

    if print_text:
        print(slack_text)
    else:
        print('Slack text generated')
    return slack_text


# create the text to send to slack
# slack_text = create_slack_text(filename, df)


# %%


def send_to_slack(slack_text):
    """Send results to a channel on Slack"""
    print('Sending results to slack')
    try:
        response = requests.post(
            os.environ['SLACK_WEBHOOK_URL'],
            data=json.dumps({'text': slack_text}),
            headers={'Content-Type': 'application/json'})
        print('Slack response: ' + str(response.text))
    except:
        print('Connection to Slack could not be established.')


# send text to slack
# send_to_slack(slack_text)


@app.route('/search')
def search():
    filter = request.args.get('filter', default='', type=str)
    # filter by keywords
    res = filter_by_keywords(df, filter).to_json()

    return res
