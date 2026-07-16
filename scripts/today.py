import datetime
import hashlib
import os
import sys
import time

import requests
from dateutil import relativedelta
from lxml import etree

# Fine-grained personal access token with All Repositories access:
# Account permissions: read:Followers, read:Starring, read:Watching
# Repository permissions: read:Commit statuses, read:Contents, read:Issues, read:Metadata, read:Pull Requests
# Issues and pull requests permissions not needed at the moment, but may be used in the future
#
# Required for full GitHub stats: ACCESS_TOKEN
# Optional:
#   USER_NAME   - GitHub login (default: Patruxs)
#   BIRTHDAY    - YYYY-MM-DD for Uptime (default: GitHub account created_at, else 2002-07-05)
# Repo root is one level above scripts/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
CACHE_DIR = os.path.join(ROOT, 'cache')
USER_NAME = os.environ.get('USER_NAME', 'Patruxs')
ACCESS_TOKEN = os.environ.get('ACCESS_TOKEN', '')
HEADERS = {'authorization': 'token ' + ACCESS_TOKEN} if ACCESS_TOKEN else {}
SVG_TARGETS = [
    os.path.join(ROOT, 'assets', 'dark.svg'),
    os.path.join(ROOT, 'assets', 'light.svg'),
]
# Dot budget for the age/uptime value column
# Full row monospaced width is 54: ". Uptime:" (9) + " " + dots + " " + value
# => AGE_JUSTIFY_LEN + 11 == 54 => 43
AGE_JUSTIFY_LEN = 43
# Lang — single right-justified line (by code size across owned non-fork repos)
#   . Lang: .......... TypeScript · Java · HTML · CSS +12
#
LINE_WIDTH = 54
LANG_FIRST_PREFIX = 8  # len(". Lang: ")
LANG_VALUE_BUDGET = LINE_WIDTH - LANG_FIRST_PREFIX  # 46
LANG_TOP_N = 4  # show the N most-used languages
LANG_MAX_N = 50  # max languages counted for "+N"
LANG_SEP = " · "
QUERY_COUNT = {
    'user_getter': 0,
    'follower_getter': 0,
    'graph_repos_stars': 0,
    'recursive_loc': 0,
    'graph_commits': 0,
    'loc_query': 0,
    'languages_getter': 0,
}


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years), 
        diff.months, 'month' + format_plural(diff.months), 
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)


def graph_commits(start_date, end_date):
    """
    Uses GitHub's GraphQL v4 API to return my total commit count
    """
    query_count('graph_commits')
    query = '''
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'start_date': start_date,'end_date': end_date, 'login': USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(request.json()['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions'])


def graph_repos_stars(count_type, owner_affiliation, cursor=None, add_loc=0, del_loc=0):
    """
    Uses GitHub's GraphQL v4 API to return my total repository, star, or lines of code count.
    """
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        if count_type == 'repos':
            return request.json()['data']['user']['repositories']['totalCount']
        elif count_type == 'stars':
            return stars_counter(request.json()['data']['user']['repositories']['edges'])


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from a repository at a time
    """
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS) # I cannot use simple_request(), because I want to save the file before raising Exception
    if request.status_code == 200:
        if request.json()['data']['repository']['defaultBranchRef'] != None: # Only count commits if repo isn't empty
            return loc_counter_one_repo(owner, repo_name, data, cache_comment, request.json()['data']['repository']['defaultBranchRef']['target']['history'], addition_total, deletion_total, my_commits)
        else: return 0
    force_close_file(data, cache_comment) # saves what is currently in the file before this program crashes
    if request.status_code == 403:
        raise Exception('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text, QUERY_COUNT)


def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    """
    Recursively call recursive_loc (since GraphQL can only search 100 commits at a time) 
    only adds the LOC value of commits authored by me
    """
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else: return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]):
    """
    Uses GitHub's GraphQL v4 API to query all the repositories I have access to (with respect to owner_affiliation)
    Queries 60 repos at a time, because larger queries give a 502 timeout error and smaller queries send too many
    requests and also give a 502 error.
    Returns the total number of lines of code in all repositories
    """
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:   # If repository data has another page
        edges += request.json()['data']['user']['repositories']['edges']            # Add on to the LoC count
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges + request.json()['data']['user']['repositories']['edges'], comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count
    """
    cached = True # Assume all repositories are cached
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt') # Create a unique filename for each user
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError: # If the cache file doesn't exist, create it
        data = []
        if comment_size > 0:
            for _ in range(comment_size): data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data)-comment_size != len(edges) or force_cache: # If the number of repos has changed, or force_cache is True
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            try:
                if int(commit_count) != edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']:
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = repo_hash + ' ' + str(edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']) + ' ' + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
            except TypeError: # If the repo is empty
                data[index] = repo_hash + ' 0 0 0 0\n'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    """
    Wipes the cache file
    This is called when the number of repositories changes or when the file is first created
    """
    with open(filename, 'r') as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size] # only save the comment
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')


def add_archive():
    """
    Several repositories I have contributed to have since been deleted.
    This function adds them using their last known data
    """
    with open(os.path.join(CACHE_DIR, 'repository_archive.txt'), 'r') as f:
        data = f.readlines()
    old_data = data
    data = data[7:len(data)-3] # remove the comment block    
    added_loc, deleted_loc, added_commits = 0, 0, 0
    contributed_repos = len(data)
    for line in data:
        repo_hash, total_commits, my_commits, *loc = line.split()
        added_loc += int(loc[0])
        deleted_loc += int(loc[1])
        if (my_commits.isdigit()): added_commits += int(my_commits)
    added_commits += int(old_data[-1].split()[4][:-1])
    return [added_loc, deleted_loc, added_loc - deleted_loc, added_commits, contributed_repos]

def force_close_file(data, cache_comment):
    """
    Forces the file to close, preserving whatever data was written to it
    This is needed because if this function is called, the program would've crashed before the file is properly saved and closed
    """
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt')
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. The file,', filename, 'has had the partial data saved and closed.')


def stars_counter(data):
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def languages_getter(username):
    """
    Aggregate languages across owned non-fork repos (by total bytes of code).
    Returns a size-descending list of language names (all of them, up to LANG_MAX_N).
    Uses GraphQL when ACCESS_TOKEN is set; else public REST.
    """
    query_count('languages_getter')
    totals = {}

    if ACCESS_TOKEN:
        cursor = None
        while True:
            query = '''
            query ($login: String!, $cursor: String) {
              user(login: $login) {
                repositories(
                  first: 50
                  after: $cursor
                  ownerAffiliations: [OWNER]
                  isFork: false
                  orderBy: {field: UPDATED_AT, direction: DESC}
                ) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
                      edges { size node { name } }
                    }
                  }
                }
              }
            }'''
            variables = {'login': username, 'cursor': cursor}
            request = simple_request(languages_getter.__name__, query, variables)
            data = request.json()['data']['user']['repositories']
            for node in data['nodes']:
                langs = (node.get('languages') or {}).get('edges') or []
                for edge in langs:
                    name = edge['node']['name']
                    totals[name] = totals.get(name, 0) + int(edge['size'])
            if not data['pageInfo']['hasNextPage']:
                break
            cursor = data['pageInfo']['endCursor']
    else:
        # Public REST fallback (no token)
        page = 1
        headers = HEADERS or {'Accept': 'application/vnd.github+json'}
        while True:
            resp = requests.get(
                f'https://api.github.com/users/{username}/repos',
                params={'per_page': 100, 'page': page, 'type': 'owner', 'sort': 'updated'},
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                raise Exception(
                    'languages_getter REST list failed',
                    resp.status_code,
                    resp.text[:200],
                )
            repos = resp.json()
            if not repos:
                break
            for repo in repos:
                if repo.get('fork'):
                    continue
                lr = requests.get(
                    repo['languages_url'],
                    headers=headers,
                    timeout=30,
                )
                if lr.status_code != 200:
                    continue
                for name, size in lr.json().items():
                    totals[name] = totals.get(name, 0) + int(size)
            if len(repos) < 100:
                break
            page += 1

    if not totals:
        return []

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _size in ranked[:LANG_MAX_N]]


def pack_lang_chunks(names):
    """
    Top LANG_TOP_N languages on one line, plus " +N" for the rest.

        . Lang: .......... TypeScript · Java · HTML · CSS +12

    Returns a one-element list for compatibility with lang_rows / svg_overwrite.
    """
    if not names:
        return ["N/A"]

    shown = names[:LANG_TOP_N]
    extra = max(0, len(names) - len(shown))
    text = LANG_SEP.join(shown)

    if extra > 0:
        suffix = f" +{extra}"
        while shown and len(text) + len(suffix) > LANG_VALUE_BUDGET:
            shown.pop()
            extra = len(names) - len(shown)
            suffix = f" +{extra}"
            text = LANG_SEP.join(shown)
        text = (text + suffix) if shown else f"+{extra}"
    else:
        while len(text) > LANG_VALUE_BUDGET and len(shown) > 1:
            shown.pop()
            text = LANG_SEP.join(shown)
        if len(text) > LANG_VALUE_BUDGET:
            text = text[:LANG_VALUE_BUDGET]

    return [text]


def lang_dots_for(value: str, prefix_len: int = LANG_FIRST_PREFIX) -> str:
    """
    Filler between ': ' and the value.

    Prefer a visible run of dots with a trailing space when there is room:
      . Lang: .......... TypeScript · Java · …
    """
    room = LINE_WIDTH - prefix_len - len(value)
    if room <= 0:
        return ""
    if room == 1:
        return " "
    # dots + trailing space (e.g. room=11 → ".......... ")
    return ("." * (room - 1)) + " "


def svg_overwrite(
    filename,
    age_data,
    commit_data=None,
    star_data=None,
    repo_data=None,
    contrib_data=None,
    follower_data=None,
    loc_data=None,
    lang_data=None,
):
    """
    Parse SVG files and update elements with uptime/age and optional GitHub stats.
    Only IDs that exist in the SVG are written (missing ones are skipped).

    lang_data: str | list[str] | None
      - str: single Lang value (legacy)
      - list: multi-line chunks (primary + continuation rows)
    """
    tree = etree.parse(filename)
    root = tree.getroot()
    # Uptime line in assets/dark.svg and assets/light.svg (ids: age_data, age_data_dots)
    justify_format(root, 'age_data', age_data, AGE_JUSTIFY_LEN)
    # Lang: single right-justified line (ids: lang_data, lang_data_dots)
    if lang_data is not None:
        chunks = lang_data if isinstance(lang_data, list) else [lang_data]
        text = chunks[0] if chunks else "N/A"
        find_and_replace(root, "lang_data", text)
        find_and_replace(root, "lang_data_dots", lang_dots_for(text, LANG_FIRST_PREFIX))
    if commit_data is not None:
        justify_format(root, 'commit_data', commit_data, 22)
    if star_data is not None:
        justify_format(root, 'star_data', star_data, 14)
    if repo_data is not None:
        justify_format(root, 'repo_data', repo_data, 6)
    if contrib_data is not None:
        justify_format(root, 'contrib_data', contrib_data)
    if follower_data is not None:
        justify_format(root, 'follower_data', follower_data, 10)
    if loc_data is not None:
        justify_format(root, 'loc_data', loc_data[2], 9)
        justify_format(root, 'loc_add', loc_data[0])
        justify_format(root, 'loc_del', loc_data[1], 7)
    # Keep SVG without XML declaration so GitHub raw/README embedding stays clean
    tree.write(filename, encoding='utf-8', xml_declaration=False)


def justify_format(root, element_id, new_text, length=0):
    """
    Updates and formats the text of the element, and modifes the amount of dots in the previous element to justify the new text on the svg
    """
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    find_and_replace(root, element_id, new_text)
    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: '', 1: ' ', 2: '. '}
        dot_string = dot_map[just_len]
    else:
        dot_string = ' ' + ('.' * just_len) + ' '
    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds the element in the SVG file and replaces its text with a new value
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is None:
        # Fallback for namespaced SVGs / odd trees
        for el in root.iter():
            if el.get('id') == element_id:
                element = el
                break
    if element is not None:
        element.text = new_text
        return True
    return False


def commit_counter(comment_size):
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt') # Use the same filename as cache_builder
    with open(filename, 'r') as f:
        data = f.readlines()
    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """
    query_count('user_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']

def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    query_count('follower_getter')
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    """
    Counts how many times the GitHub GraphQL API is called
    """
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    """
    Calculates the time it takes for a function to run
    Returns the function result and the time differential
    """
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    """
    Prints a formatted time differential
    Returns formatted result if whitespace is specified, otherwise returns raw result
    """
    print('{:<23}'.format('   ' + query_type + ':'), sep='', end='')
    print('{:>12}'.format('%.4f' % difference + ' s ')) if difference > 1 else print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return


def resolve_start_date():
    """
    Uptime start date:
      1) BIRTHDAY env (YYYY-MM-DD)
      2) GitHub account created_at (public REST, no token needed)
      3) Fallback 2002-07-05 (original template default)
    """
    birthday_env = os.environ.get('BIRTHDAY', '').strip()
    if birthday_env:
        return datetime.datetime.strptime(birthday_env, '%Y-%m-%d')

    try:
        resp = requests.get(
            f'https://api.github.com/users/{USER_NAME}',
            headers=HEADERS or None,
            timeout=20,
        )
        if resp.status_code == 200:
            created = resp.json().get('created_at')  # e.g. 2021-09-07T05:41:30Z
            if created:
                return datetime.datetime.fromisoformat(
                    created.replace('Z', '+00:00')
                ).replace(tzinfo=None)
    except Exception as exc:
        print(f'Warning: could not fetch account created_at ({exc})')

    return datetime.datetime(2002, 7, 5)


if __name__ == '__main__':
    """
    Based on Andrew Grant (Andrew6rant), 2022-2025
    Adapted for Patruxs profile banners (assets/dark.svg and assets/light.svg).
    """
    print('Calculation times:')
    start_date, start_time = perf_counter(resolve_start_date)
    formatter('start date resolve', start_time)
    print(f"   uptime since:          {start_date.date().isoformat()}")

    age_data, age_time = perf_counter(daily_readme, start_date)
    formatter('uptime calculation', age_time)
    print(f"   uptime text:           {age_data}")

    # Always refresh Lang from repository language stats (ALL languages by size)
    lang_names, lang_time = perf_counter(languages_getter, USER_NAME)
    formatter('languages', lang_time)
    lang_chunks = pack_lang_chunks(lang_names)
    print(f"   lang names:       {len(lang_names)} → {lang_names}")
    print(f"   lang rows:        {lang_chunks}")

    commit_data = star_data = repo_data = contrib_data = follower_data = None
    loc_slice = None
    user_time = loc_time = commit_time = star_time = repo_time = contrib_time = follower_time = 0.0
    owner_id = None

    if ACCESS_TOKEN:
        user_data, user_time = perf_counter(user_getter, USER_NAME)
        owner_id, acc_date = user_data
        # Used by loc_counter_one_repo when counting authored commits
        globals()['OWNER_ID'] = owner_id
        formatter('account data', user_time)

        total_loc, loc_time = perf_counter(
            loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7
        )
        if total_loc[-1]:
            formatter('LOC (cached)', loc_time)
        else:
            formatter('LOC (no cache)', loc_time)
        commit_data, commit_time = perf_counter(commit_counter, 7)
        star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
        formatter('stars', star_time)
        repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
        formatter('repos', repo_time)
        contrib_data, contrib_time = perf_counter(
            graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER']
        )
        formatter('contributed repos', contrib_time)
        follower_data, follower_time = perf_counter(follower_getter, USER_NAME)
        formatter('followers', follower_time)

        # several repositories that I've contributed to have since been deleted.
        if owner_id == {'id': 'MDQ6VXNlcjU3MzMxMTM0'}:  # only for Andrew6rant
            archived_data = add_archive()
            for index in range(len(total_loc) - 1):
                total_loc[index] += archived_data[index]
            contrib_data += archived_data[-1]
            commit_data += int(archived_data[-2])

        for index in range(len(total_loc) - 1):
            total_loc[index] = '{:,}'.format(total_loc[index])
        loc_slice = total_loc[:-1]
    else:
        print('   ACCESS_TOKEN not set — skipping stars/LOC/etc. (Lang still updated)')

    # Rebuild SYSTEM.INFO structure so multi-line Lang rows exist
    try:
        from pathlib import Path as _Path

        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        from update_system_info import CONFIG, build_rows, load_config, patch_svg

        cfg = load_config(CONFIG)
        rows = build_rows(cfg, lang_chunks=lang_chunks)
        for svg_path in SVG_TARGETS:
            if os.path.isfile(svg_path):
                patch_svg(_Path(svg_path), rows)
    except Exception as rebuild_exc:
        print(f'WARNING: structure rebuild failed ({rebuild_exc}); writing live fields only')

    for svg_path in SVG_TARGETS:
        if not os.path.isfile(svg_path):
            print(f'WARNING: skip missing {svg_path}')
            continue
        svg_overwrite(
            svg_path,
            age_data,
            commit_data,
            star_data,
            repo_data,
            contrib_data,
            follower_data,
            loc_slice,
            lang_chunks,
        )
        print(f'   updated {os.path.basename(svg_path)}')

    total = (
        user_time
        + age_time
        + lang_time
        + loc_time
        + commit_time
        + star_time
        + repo_time
        + contrib_time
        + follower_time
    )
    print('{:<21}'.format('Total function time:'), '{:>11}'.format('%.4f' % total), ' s')
    print('Total GitHub GraphQL API calls:', '{:>3}'.format(sum(QUERY_COUNT.values())))
    for funct_name, count in QUERY_COUNT.items():
        print('{:<28}'.format('   ' + funct_name + ':'), '{:>6}'.format(count))
