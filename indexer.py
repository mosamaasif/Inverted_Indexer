import os
import io
import platform
import json
import nltk
import heapq
import time
from rich.progress import (
    TextColumn,
    BarColumn,
    Progress,
    TimeRemainingColumn,
    TimeElapsedColumn
)
from rich import print
from rich import box
from rich.panel import Panel
from math import sqrt
from bs4 import BeautifulSoup
from nltk.stem import snowball
from nltk.corpus import stopwords
from collections import defaultdict
from nltk.tokenize import word_tokenize, sent_tokenize

SNOWBALL_STEMMER = snowball.SnowballStemmer('english')
STOP_WORDS = None
PATH_SEP = '/' if platform.system().lower() == 'darwin' else "\\"
HITS_JSON = None


# Prints headers of sections
def print_header(title, msg, val=None):
    string = f'[bold green]{msg}[/bold green]'
    if val is not None:
        string += f' [bold italic]{val}[/bold italic]'

    print()
    print(Panel(string, expand=False, box=box.ROUNDED, title=title), end='\n\n')

    time.sleep(0.7)


# Prints success msgs
def print_success(msg, val=None):
    string = f'[bold green]{msg}[/bold green]'
    if val is not None:
        string += f' [bold italic]{val}[/bold italic]'

    print(string, end='\n')

    time.sleep(0.3)


# updates stopwords as well as punctuations for nltk
def init():
    print_header('INIT', 'Initializing')

    nltk.download('stopwords')
    nltk.download('punkt')
    global STOP_WORDS
    STOP_WORDS = stopwords.words('english')

    if os.path.isfile('query_hits.json') and os.access('query_hits.json', os.R_OK):
        with io.open('query_hits.json', encoding='utf-8', mode='r') as jf:
            global HITS_JSON
            HITS_JSON = json.load(jf)
    else:
        HITS_JSON = {}


# Uses BeautifulSoup to parse html file and get strings from it's body
def fetch_html_text(data):
    soup = BeautifulSoup(data, 'html.parser')
    body = soup.body
    html_txt = []
    if body is not None:
        html_txt = [text.lower().encode('unicode_escape')
                    .decode('unicode_escape')
                    for text in body.stripped_strings]

    return html_txt


# Uses nltk to tokenize words and
# get unique (alphabetical) tokens as well
def tokenize(txt_strs):
    actual_tokens = []
    for s in txt_strs:
        toks = word_tokenize(s)
        actual_tokens += [tok.lower() for tok in toks if tok.isalpha()]

    return actual_tokens, set(actual_tokens)


# Finds position of tokens in doc
def find_words_positions(a_tokens, u_toks):
    words_pos = dict()

    for idx, a_token in enumerate(a_tokens):
        stemmed_tok = SNOWBALL_STEMMER.stem(a_token)

        if stemmed_tok in u_toks:
            if stemmed_tok not in words_pos:
                words_pos[stemmed_tok] = [idx]
            else:
                words_pos[stemmed_tok].append(idx)

    return words_pos


# Task-1: Preprocessing the files in a sub directory passed as parameter
def pre_processing(sub_dir_path):

    data = []
    d_info = {}
    data_files = [filename for filename in os.listdir(sub_dir_path)]

    print_header('PRE-PROCESSOR', 'Preprocessing Directory', val=sub_dir_path)

    doc_curr = 0
    p_prog = Progress(
        TextColumn('[bold yellow]Preprocessing [/bold yellow][italic blue]{task.fields[pfile]}[/italic blue]'),
        BarColumn(bar_width=20),
        '[progress.percentage]{task.percentage:>3.1f}%',
        "•",
        TimeRemainingColumn(),
        "•",
        TimeElapsedColumn(),
        "•",
        '[bold green italic]{task.fields[currF]}/{task.fields[totalF]}[/bold green italic]')

    with p_prog:
        task_id = p_prog.add_task("Pre-Processing", total=len(data_files), pfile='',
                                  currF='', totalF=len(data_files))

        for file in data_files:
            p_prog.update(task_id=task_id, completed=doc_curr, pfile=file, currF=doc_curr)

            complete_file_path = os.path.join(sub_dir_path, file)
            with open(complete_file_path, encoding='utf-8', mode='r') as f:
                try:
                    # Getting tokens
                    actual_tokens, unique_tokens = tokenize(fetch_html_text(f.read()))

                    # Stop Wording
                    # Using set since looping over the
                    # lists takes alot of time for larger files
                    unique_tokens = unique_tokens - set(STOP_WORDS)

                    # Stemming
                    unique_tokens = set([SNOWBALL_STEMMER.stem(tok) for tok in unique_tokens])

                    # Finding position of words in the doc
                    words_pos = find_words_positions(actual_tokens, unique_tokens)
                    mag = sqrt(sum([len(item[1]) ** 2 for item in words_pos.items()]))

                except Exception as ex:
                    doc_curr += 1
                    continue

                doc_curr += 1
                d_info[doc_curr] = {'len': len(actual_tokens), 'mag': mag, 'path': complete_file_path}
                data.append([doc_curr, unique_tokens, words_pos])
        p_prog.update(task_id=task_id, completed=doc_curr, pfile=file, currF=doc_curr)

    print_success('Preprocessing Completed for', val=sub_dir_path)

    return data, d_info


# Task-2: This generates in memory inverted index for one BLOCK
def gen_block_inverted_index(data, block):

    print_header('INDEX GENERATOR', 'Generating Inverted Index for BLOCK', val=block)

    block_inverted_index = defaultdict(list)

    for [d_id, stemmed_words, words_pos] in data:
        for word in list(stemmed_words):
            w_pos = words_pos[word]
            block_inverted_index[word].append({
                'docID': d_id,
                'term_freq': len(w_pos),
                'positions': w_pos
            })

    print_success('Generated Inverted Index for', val=block)

    return dict(sorted(block_inverted_index.items()))


# Task-2: This function saves posting list to file, applying delta encoding
def save_posting_list(p_fd, p_list):
    byte = 0

    # Document freq for token
    byte += p_fd.write(f'{len(p_list)},')

    for p_val in p_list:
        byte += p_fd.write(f"{p_val['docID']},")
        byte += p_fd.write(f"{p_val['term_freq']},")

        positions = p_val['positions']

        # delta encode the positions if the tf > 1
        tf = p_val['term_freq']
        if tf > 1:
            positions = [positions[0]] + [positions[i] - positions[i - 1] for i in range(1, tf)]
        else:
            positions = [positions[0]]

        for pos in positions:
            byte += p_fd.write(f'{pos},')

    if platform.system().lower() == 'darwin':
        byte += p_fd.write('\n')
    else:
        byte += p_fd.write('\n') + 1

    return byte


# Task-2: This function writes the inverted index for one BLOCK into a file
def store_block_inverted_index(s_dir, block_inverted_index):

    print_header('BLOCK SAVE', 'Saving Inverted Index for BLOCK', val=s_dir)

    dir_name = s_dir[s_dir.rfind(PATH_SEP) + 1:]
    with open(f'index_{dir_name}_postings.txt', encoding='utf-8', mode='w') as p_file:
        with open(f'index_{dir_name}_terms.txt', encoding='utf-8', mode='w') as t_file:
            byte_pos = 0

            for key in block_inverted_index.keys():
                t_file.write(f'{key}, {byte_pos}\n')
                byte_pos += save_posting_list(p_file, block_inverted_index[key])

    print_success('Stored Inverted Index for BLOCK', val=s_dir)


# This function generates complete inverted index
def gen_complete_inverted_index(sub_dirs):

    # This is Task 4, docInfo file
    # Getting all the doc infos and then storing once in the end
    d_info_all = {}

    for sub_dir in sub_dirs:
        # For each sub directory (or BLOCK) inside corpus1
        # Task 1
        data, d_info = pre_processing(sub_dir)

        # Updating accumulated docInfo dictionary
        d_info_all.update(d_info)

        # Creating the Inverted Index for this BLOCK
        block_inverted_index = gen_block_inverted_index(data, sub_dir)

        # Storing the Inverted Index in file
        store_block_inverted_index(sub_dir, block_inverted_index)

    # Task-4: Stores docInfo file
    with open('docInfo.txt', encoding='utf-8', mode='w') as f:
        f.write(json.dumps(d_info_all))


# This reads posting list from the previously stored files
def read_posting_list(fd):

    p_list = list()
    line = fd.readline()
    tokens = [int(token) for token in line.split(',') if token.isnumeric()]

    idx = 1
    # Loops as per doc freq
    for _ in range(tokens[0]):
        posting = {'docID': tokens[idx]}
        posting['term_freq'] = tokens[idx + 1]
        posting['positions'] = [tokens[idx + 2]]
        idx += 3

        for i in range(posting['term_freq'] - 1):
            # Reversing delta encoding
            posting['positions'].append(posting['positions'][i] + tokens[idx])
            idx += 1

        p_list.append(posting)

    return p_list


# Task-3: Merges Sorted Indices
def merge_indices(sub_dirs):
    print_header('MERGER', 'Merging Indices')

    byte_pos = 0
    u_words_count = 0

    file_names = [s_dir[s_dir.rfind(PATH_SEP) + 1:] for s_dir in sub_dirs]

    idx_terms_fds = [open(f'index_{fff}_terms.txt', encoding='utf-8', mode='r')
                     for fff in file_names]
    idx_posting_fds = [open(f'index_{fff}_postings.txt', encoding='utf-8', mode='r')
                       for fff in file_names]

    merged_idx_terms_fd = open('inverted_index_terms.txt', encoding='utf-8', mode='w')
    merged_idx_posting_fd = open('inverted_index_postings.txt', encoding='utf-8', mode='w')

    # Get first line of each index_{}_terms.txt file
    idx_terms_lines = {idx: fd.readline() for idx, fd in enumerate(idx_terms_fds)}

    # Until nothing unmerged left
    while len(idx_terms_lines) > 0:
        # Extracting (term, byte position for posting list in other file) for
        # each line in index_terms files
        idx_terms = [(key, idx_terms_lines[key].split(', ')[0],
                      int(idx_terms_lines[key].split(', ')[1]))
                     for key in idx_terms_lines.keys()]

        # Finding the minimum term to merge
        min_term = idx_terms[0][1]
        for _, w, _ in idx_terms:
            if w < min_term:
                min_term = w

        # Save the minimums if multiple of same word found
        min_terms = [(doc_id, term, b) for (doc_id, term, b) in idx_terms if term == min_term]
        u_words_count += 1

        # Merge the next (word, posting list) pair and
        # ++ the relevant idx_terms fds (move a byte forward)
        merged_posting_list = []
        for (doc_id, _, b) in min_terms:

            # Retrieve relevant posting list from opened file to merge
            idx_posting_fds[doc_id].seek(b, 0)

            # Merge the lists together
            merged_posting_list = list(heapq.merge(merged_posting_list,
                                       read_posting_list(idx_posting_fds[doc_id]),
                                       key=lambda val: val['docID']))

            # Fetch the next doc, line data
            idx_terms_lines[doc_id] = idx_terms_fds[doc_id].readline()

        # Writing current min term in index
        merged_idx_terms_fd.write(f'{min_term}, {byte_pos}\n')

        # Writing minimum term's merged posting list in merged_idx_posting file
        # and updating byte_pos
        byte_pos += save_posting_list(merged_idx_posting_fd, merged_posting_list)

        # Checking to remove completely merged files
        idx_terms_lines = {key: idx_terms_lines[key] for key in idx_terms_lines.keys()
                           if idx_terms_lines[key] != ''}

    print_success('Successfully Merged indices, unique words found', val=u_words_count)


# Reading inverted index data
def load_inverted_index_terms(path):

    data = {}
    with open(path, encoding='utf-8', mode='r') as f:

        lines = f.readlines()
        for line in lines:

            tok = line.strip().split(', ')
            data[tok[0]] = int(tok[1])

    return data


# This uses boolean retrieval to search query
def boolean_retrieval(query, data, doc_info_all):
    print_header('BOOLEAN RETRIEVAL', 'Searching for', val=query)

    start_time = time.time()

    # Tokenizing query, and storing lower case, if not character or anything
    tokens = []
    for s in sent_tokenize(query):
        toks = word_tokenize(s)
        tokens += [t.lower() for t in toks if t.isalpha()]

    # Stop Wording
    unique_tokens = list(set(tokens) - set(STOP_WORDS))

    # Stemming
    stemmed_words = [SNOWBALL_STEMMER.stem(tok) for tok in unique_tokens]

    query_hits = []
    with open('inverted_index_postings.txt', encoding='utf-8', mode='r') as p_file:
        for word in stemmed_words:
            if word in data:
                posting_location = data[word]
                p_file.seek(posting_location)
                posting_list = read_posting_list(p_file)

                for posting in posting_list:
                    query_hits.append(doc_info_all[str(posting['docID'])]['path'])

    if len(query_hits) > 0:
        end_time = time.time()
        print(f'[bold]Found [/bold][bold italic green]{len(query_hits)} [/bold italic green]'
              '[bold]matches in [bold]'
              f'[bold italic green]{(end_time - start_time):.3f} [/bold italic green]'
              '[bold]secs[/bold]',
              end='\n\n')

        query_hits.sort()
        string = ""
        for hit in query_hits:
            string += hit[hit.rfind('corpus') + len('corpus') + len(PATH_SEP) + 1:] + '\n'
        print(Panel(string, expand=False, box=box.ROUNDED, title="QUERY HITS"), end='\n\n')
    else:
        print('\n\n[bold red]No Match Found[/bold red]', end='\n\n')


# Task-5: Boolean Retrieval and searching
def search_query(query):

    try:
        with open('docInfo.txt', encoding='utf-8', mode='r') as f:

            data = load_inverted_index_terms('inverted_index_terms.txt')

            doc_info_all = json.loads(f.read())

            boolean_retrieval(query, data, doc_info_all)

    except Exception as ex:
        print('[bold red][SEARCH][/bold red] -> '
              f'Failed to Search \n\t[yellow italic]EXCEPTION[/yellow italic]: {ex}', end='\n\n')


# Prints Menu
def print_menu():
    print_header("", "MENU")
    print('[green bold]1)[/green bold] Search Only\n'
          '[green bold]2)[/green bold] Rebuild Index and Search\n'
          '[green bold]3)[/green bold] Exit\n')


# Entry Point
if __name__ == '__main__':

    init()

    while(True):
        print_menu()
        print('[yellow bold italic]Enter Option[/yellow bold italic]: ', end='')
        opt = input()

        if not opt.isdigit() or int(opt) > 3 or int(opt) < 1:
            print('[bold red]Enter a value between 1 and 3![/bold red]', end='\n\n')
        elif opt == '3':
            break
        else:
            flag = False
            if opt == '2':
                main_dir_path = input('Enter Cropus path: ')

                if os.path.exists(main_dir_path):
                    # Sorting since by default it uses the sequence
                    # by which files are indexed by the File System
                    # so may not be in expected order
                    sub_dirs = sorted([s_dir for s_dir in os.listdir(
                                       main_dir_path) if not s_dir.startswith('.')])
                    # Turning into complete paths
                    sub_dirs = [os.path.join(main_dir_path, s_dir) for s_dir in sub_dirs]

                    gen_complete_inverted_index(sub_dirs)
                    merge_indices(sub_dirs)
                    flag = True
                else:
                    print(f"\nCorpus Path '{main_dir_path}' does not exist!")

            if flag or opt == '1':
                print_header("", "SEARCH QUERY")
                print('[yellow bold italic]Enter Query[/yellow bold italic]: ', end='')
                query = input()
                if len(query) > 0:
                    search_query(query)
                else:
                    print("[red bold]Query cannot be empty[/red bold]")
