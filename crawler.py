import sys
import time
import json
import argparse

from scrapers import scrape_set
from functions.browser import (
    create_browser, get_page_source, BadProxyException)


def crawl(autocrawl=False, sleeptime=5, max=None, nodb=False,
          headless=False, queue=[], blacklist=set(),
          proxies=[], timeout=3):

    if not nodb:
        # Additional imports
        from database import create_database_connection, upload_set

        # Establish Database connection
        try:
            conn = create_database_connection()
        except Exception as e:
            print(e)
            sys.exit()

    # Scrape tracks
    driver = None
    urls = queue
    urls_scraped = set()
    error_count = 0
    proxy_index = 0
    while(len(urls) > 0):
        num_current = len(urls_scraped) + 1
        num_overall = str(len(urls) + len(urls_scraped)) + ("+" if autocrawl else "")

        # Create Browser
        if(len(proxies) > 0):
            if(num_current % 10 == 0 or driver is None):
                proxy_index += 1
                if(driver is not None):
                    driver.quit()

                if(proxy_index > len(proxies)):
                    proxy_index = 0

                # Wait for a config with a working Proxy
                try:
                    driver = create_browser(headless=headless,
                                            proxy=proxies[proxy_index],
                                            timeout=timeout)
                except BadProxyException as e:
                    proxies.remove(proxies[proxy_index])
                    continue
        else:
            driver = create_browser(headless=headless, timeout=timeout)

        # Exit if enough sets are scraped is reached
        if(max is not None and max < num_current):
            break

        print("Scraping url %s of %s" % (num_current, num_overall))

        url = urls[0]
        if(url == "" or url is None):
            continue

        if(url in blacklist):
            print("Url was found in the blacklist, skipping")
            urls_scraped.add(urls.pop(0))
            continue

        print("Scraping %s:" % url)

        try:
            html = get_page_source(driver, url, autocrawl=autocrawl)
        except Exception as e:
            if(error_count >= 3):
                print("Couldn't recieve page source. Error %s, skipping" % e)
                urls_scraped.add(urls.pop(0))
                error_count = 0
                continue
            else:
                print("Couldn't recieve page source retrying")
                error_count += 1
                continue

        try:
            setlist = scrape_set(html, url)
        except Exception as e:
            if(error_count >= 3):
                print("Couldn't scrape set because of %s, skipping" % e)
                urls_scraped.add(urls.pop(0))
                error_count = 0
                continue
            else:
                print("Couldn't scrape set retrying")
                error_count += 1
                continue

        # Save the scraped information
        if not nodb:
            upload_set(conn, setlist)
        else:
            try:
                with open("output.json", "r+") as f:
                    data = json.load(f)
            except Exception as e:
                data = []

            data.append(setlist)

            with open("output.json", "w+") as f:
                f.write(json.dumps(data))

        # Add links to queue
        if(autocrawl):
            if(setlist["previous_set"]):
                url = setlist["previous_set"]
                if not (url in urls) and not (url in urls_scraped) and not (url in blacklist):
                    urls.append(url)
                    print("Added previous setlist %s to queue."
                          % setlist["previous_set"])

            if(setlist["next_set"]):
                url = setlist["next_set"]
                if not (url in urls) and not (url in urls_scraped) and not (url in blacklist):
                    urls.append(url)
                    print("Added next setlist %s to queue."
                          % setlist["next_set"])

            for link in setlist["artist_links"]:
                url = link
                if not (url in urls) and not (url in urls_scraped) and not (url in blacklist):
                    urls.append(url)
                    print("Added artist setlist %s to queue." % link)

            for link in setlist["related_links"]:
                url = link
                if not (url in urls) and not (url in urls_scraped) and not (url in blacklist):
                    urls.append(url)
                    print("Added related setlist %s to queue." % link)

        # Move url to already scraped
        urls_scraped.add(urls.pop(0))

        time.sleep(sleeptime)

    # Clear queue.txt & close browsers
    print("Scraped %s sets" % num_current)
    driver.quit()


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser()

    parser.add_argument("-a", "--autocrawl",
                        help="automatically add urls to queue",
                        action="store_true")
    parser.add_argument("-s", "--sleeptime", type=int)
    parser.add_argument("-t", "--timeout", type=int)
    parser.add_argument("--max", type=int)
    parser.add_argument("--nodb",
                        help="disable the database connection and scrape to a file instead",
                        action="store_true")
    parser.add_argument("--headless",
                        help="run chrome in headless mode",
                        action="store_true")
    parser.add_argument('--blacklistfile',
                        help="path to a txt file with links (one per line)")
    parser.add_argument('--proxyfile',
                        help="path to a txt file with proxies (one per line)")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--queuefile',
                        help="path to a txt file with links (one per line)")
    source.add_argument('--queue',
                        nargs='+',
                        help="links to start scraping")

    args = parser.parse_args()

    if(args.autocrawl):
        autocrawl = True
        print("Automatic crawling is turned on")
    else:
        autocrawl = False

    if(args.sleeptime):
        if args.sleeptime > 4:
            sleeptime = args.sleeptime
            print("Sleeptime is set to %s" % sleeptime)
        else:
            sleeptime = 5
            print("Sleeptime needs to be a minimum of 5 seconds")
    else:
        sleeptime = 5

    if(args.max):
        if args.max > 0:
            max = args.max
            print("Maximum number of sets is set to %s" % max)
        else:
            max = None
            print("Maximum number of sets needs to be positive")
    else:
        max = None

    if(args.timeout):
        if(args.timeout > 3):
            timeout = args.timeout
            print("Timeout is set to %s" % timeout)
        else:
            timeout = 3
            print("Timeout needs to be a minimum of 3 seconds")
    else:
        timeout = 10

    if(args.nodb):
        nodb = True
    else:
        nodb = False

    if(args.headless):
        headless = True
    else:
        headless = False

    queue = []
    if(args.queuefile):
        with open(args.queuefile) as f:
            for line in f:
                queue.append(line.strip())
    elif(args.queue):
        queue.extend(args.queue)

    blacklist = set()
    if(args.blacklistfile):
        with open(args.blacklistfile) as f:
            for line in f:
                blacklist.add(line.strip())

    proxies = []
    if(args.proxyfile):
        with open(args.proxyfile) as f:
            for line in f:
                proxies.append(line.strip())

    # Crawl
    crawl(autocrawl=autocrawl, sleeptime=sleeptime, nodb=nodb,
          headless=headless, queue=queue, max=max, blacklist=blacklist,
          proxies=proxies, timeout=timeout)

    # Clear queue
    if args.queuefile:
        open("queue.txt", 'w').close()
