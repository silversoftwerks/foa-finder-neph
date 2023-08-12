import json
from autoscraper import AutoScraper
from flask import Flask, request

url = 'https://do303.com/events/live-music/today'

wanted_list = ["Maggie Rogers","https://maps.google.com/?q=17598 West Alameda Parkway, Morrison, CO, 80465", "7:30PM"]

scraper=AutoScraper()
result=scraper.build(url,wanted_list)
results = scraper.get_result_exact(url, grouped=True)
# result_event = scraper.get_result_similar(url=url, wanted_list=wanted_list)
scraper.keep_rules(results.keys())
titles=['Name',"location","time"]
print(list(results.keys()))
print(dict((a, titles[i]) for i, a in enumerate(list(results.keys())[0:3])))
scraper.set_rule_aliases(dict((a, titles[i]) for i, a in enumerate(list(results.keys())[0:3])))
scraper.save('do303-search')
# scraper.save("do303-search")

scraper.load('do303-search')
app = Flask(__name__)



def write_to_file(filename, *strings):
    # Open the file in write mode
    file = open(filename, "w")
    
    json.dump(strings, file)
    
    # Close the file
def get_do303_result(search_query):
    url = 'https://do303.com/events/live-music/today'
    result = scraper.get_result_similar(url, group_by_alias=True)
    return _aggregate_result(result)

def _aggregate_result(result):
    final_result = []
    print(list(result.values())[0])
    for i in range(len(list(result.values())[0])):
        try:
            
            final_result.append({alias: result[alias][i] for alias in result})
        except:
            pass
    return final_result
# Example usage:
# print(result_event)
# write_to_file("output.txt", result)
@app.route('/')
def home():
    query = request.args.get('q')
    print(query)
    return dict(result=get_do303_result(query))
