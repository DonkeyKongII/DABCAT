import os
import re
import json
import tarfile
import distutils
from distutils import dir_util
import py_compile
import click

from pyfiglet import figlet_format
from PyInquirer import (Token, ValidationError, Validator, print_json, prompt, style_from_dict)

try:
    import colorama
    colorama.init()
except ImportError:
    colorama = None

try:
    from termcolor import colored
except ImportError:
    colored = None

IMPORTANT_FILES = {
    'connector_file': None,
    'connector_data': None,
    'metadata_file': None,
    'metadata_data': None,
    'replacerizer_file': None,
    'replacerizer_data': None,
    'dummy_data': []
}

PREAMBLE = '' \
        '{tab}{tab}#####################################\n' \
        '{tab}{tab}#### start DABCAT generated code ####\n' \
        '{tab}{tab}#####################################\n'

POSTAMBLE = '' \
        '{tab}{tab}#####################################\n' \
        '{tab}{tab}#### stop DABCAT generated code #####\n' \
        '{tab}{tab}#####################################\n'

style = style_from_dict({
    Token.QuestionMark: '#E91E63 bold',
    Token.Selected: '#673AB7 bold',
    Token.Instruction: '',  # default
    Token.Answer: '#2196f3 bold',
    Token.Question: '',
})

class file_validator(Validator):
    def validate(self, file_to_open):
        if len(file_to_open.text):
            try:
                with open(file_to_open.text, 'r') as opened_file:
                    return True
            except Exception as err:
                raise ValidationError(
                    message="File could not be found, or could not be opened. Details - {}".format(err.message),
                    cursor_position=len(file_to_open.text)
                )
        else:
            raise ValidationError(
                message="This field cannot be blank",
                cursor_position=len(file_to_open.text)
            )


def output(string, color, font="chunky", figlet=False):
    if colored:
        if not figlet:
            print(
                colored(string, color)
            )
        else:
            print(
                colored(
                    figlet_format(string, font=font),
                    color
                )
            )
    else:
        print(string)


def cat_banner():
    output('''           __..--''``---....___   _..._    __
 /// //_.-'    .-/";  `        ``<._  ``.''_ `. / // /
///_.-' _..--.'_    \                    `( ) ) // //
/ (_..-' // (< _     ;_..__               ; `' / ///
 / // // //  `-._,_)' // / ``--...____..-' /// / //''', "green")


def check_folder(directory='.', file_to_find=None, file_key=None):
    for root, dirs, files in os.walk(directory):
        for file_name in files:
            if file_to_find:
                if file_to_find.lower() == file_name.lower():
                    IMPORTANT_FILES[file_key] = '{}/{}'.format(directory, file_name)
                    return True
            else:
                if file_name.lower().endswith('_connector.py'):
                    IMPORTANT_FILES['connector_file'] = '{}/{}'.format(directory, file_name)
                elif 'replacerizer' in file_name.lower():
                    IMPORTANT_FILES['replacerizer_file'] = '{}/{}'.format(directory, file_name)
                elif '.json' in file_name.lower():
                    IMPORTANT_FILES['metadata_file'] = '{}/{}'.format(directory, file_name)
                
                if IMPORTANT_FILES['connector_file'] and IMPORTANT_FILES['metadata_file'] and IMPORTANT_FILES['replacerizer_file']:
                    return True
    
    if IMPORTANT_FILES['connector_file'] or IMPORTANT_FILES['metadata_file'] or IMPORTANT_FILES['replacerizer_file']:
        return True

    return False


def validate_known_data():
    output('Here\'s what we already know:', 'blue')
    
    if IMPORTANT_FILES['connector_file']:
        output('\tconnector file: {}'.format(IMPORTANT_FILES['connector_file']), 'cyan')
    if IMPORTANT_FILES['metadata_file']:
        output('\tmetadata file: {}'.format(IMPORTANT_FILES['metadata_file']), 'cyan')
    if IMPORTANT_FILES['replacerizer_file']:
        output('\treplacerizer File: {}'.format(IMPORTANT_FILES['replacerizer_file']), 'cyan')

    output('\n', 'grey')
    if not get_confirmation('is this correct?'):
        IMPORTANT_FILES['connector_file'] = None
        IMPORTANT_FILES['metadata_file'] = None
        IMPORTANT_FILES['replacerizer_file'] = None

    return

def get_required_data():
    if not IMPORTANT_FILES['connector_file']:
        get_a_file('connector_file')
    if not IMPORTANT_FILES['metadata_file']:
        get_a_file('metadata_file')
    if not IMPORTANT_FILES['replacerizer_file']:
        if get_confirmation('do you want to use a replacerizer?'):
            get_a_file('replacerizer_file')

    return


def read_important_files():
    file_keys = [key for key in IMPORTANT_FILES.keys() if '_file' in key and IMPORTANT_FILES[key]]
    for file_key in file_keys:
        with open(IMPORTANT_FILES[file_key], 'r') as important_file:
            file_data = important_file.read()
            
            if file_key in ['metadata_file', 'replacerizer_file']:
                file_data = json.loads(file_data)
            
            IMPORTANT_FILES[file_key.replace('_file', '_data')] = file_data

    return True


def get_dummy_data():
    answers = {'more_data': True}
    while answers["more_data"]:
        answers = None
        questions = [
            {
                'type': 'input',
                'name': 'dummy_data_file',
                'message': 'dummy data file?',
                'validate': file_validator
            },
            {
                'type': 'list',
                'name': 'action_id',
                'message': 'which action identifier will this dummy data be used for?',
                'choices': [action['identifier'] for action in IMPORTANT_FILES['metadata_data']['actions']]
            },
            {
                'type': 'confirm',
                'name': 'all_responses',
                'message': 'use for all requests regardless of input?'
            },
            {
                'type': 'list',
                'name': 'parameter',
                'message': 'if not using for all requests, which parameter should be looked at to determine if dummy data should be provided?',
                'choices': lambda answers: [param for param in [action for action in IMPORTANT_FILES['metadata_data']['actions'] if action['identifier'] == answers['action_id']][0]['parameters'].keys()],
                'when': lambda answers: not(answers['all_responses'])
            },
            {
                'type': 'input',
                'name': 'parameter_value',
                'message': 'parameter value used to determine if dummy data should be provided',
                'validate': lambda val: (val or '') != '' or 'parameter value must be provided',
                'when': lambda answers: not(answers['all_responses'])
            },
            {
                'type': 'confirm',
                'name': 'more_data',
                'message': 'more dummy data?'
            }
        ]

        answers = prompt(questions)
        dummy_data = None
        try:
            dummy_data = read_dummy_data(answers['dummy_data_file'])
        except Exception as err:
            output('error occured while processing dummy data; details - {}'.format(str(err)), 'red')

        if dummy_data:
            answers['dummy_data_data'] = dummy_data
            IMPORTANT_FILES['dummy_data'].append(answers)

    return


def process_data():
    processed_actions = []
    
    handle_action_re = re.compile(r'([ ]+def handle_action\([^)]+\)\:\n)')    
    handle_action_match = handle_action_re.search(IMPORTANT_FILES['connector_data'])
    tab = ' ' * (len(handle_action_match.groups()[0]) - len(handle_action_match.groups()[0].lstrip()))

    connector_data_part_1 = IMPORTANT_FILES['connector_data'][0:handle_action_match.span()[1]]
    connector_data_part_2 = IMPORTANT_FILES['connector_data'][handle_action_match.span()[1]:]

    addition = PREAMBLE.format(tab=tab) \
        + '{tab}{tab}action = self.get_action_identifier()\n'.format(tab=tab)

    for dummy_data in IMPORTANT_FILES['dummy_data']:
        if dummy_data['action_id'] not in processed_actions:
            addition = '{addition}' \
                '{tab}{tab}if action == \'{action_id}\'{conditional}:\n' \
                '{tab}{tab}{tab}action_result = self.add_action_result(ActionResult(dict(param)))\n' \
                '{tab}{tab}{tab}action_result.update_summary({summary})\n' \
                '{add_data}' \
                '{tab}{tab}{tab}return action_result.set_status(phantom.APP_SUCCESS, \'{message}\')\n'.format(
                    tab=tab,
                    addition=addition,
                    action_id=dummy_data['action_id'],
                    conditional=(
                        ' and param.get(\'{param}\', \'\') == \'{param_val}\''.format(
                            param=dummy_data['parameter'],
                            param_val=dummy_data['parameter_value']
                        ) if dummy_data.get('parameter') else ''
                    ),
                    summary=str(dummy_data['dummy_data_data'][0]['summary']),
                    add_data=(
                        '{tab}{tab}{tab}action_result.add_data([])\n'.format(tab=tab) 
                        if len(dummy_data['dummy_data_data'][0]['data']) == 0 else 
                        ''.join([
                            '{tab}{tab}{tab}action_result.add_data({data})\n'.format(tab=tab, data=data) 
                            for data in dummy_data['dummy_data_data'][0]['data']
                        ])),
                    message=str(dummy_data['dummy_data_data'][0]['message'])
                )

    addition = '{addition}{postamble}'.format(addition=addition, postamble=POSTAMBLE.format(tab=tab))
    
    replacerizer_wholesale = r'(?:u\'\*\*\*)([^\*]+)(?:\*\*\*\')'
    replacerizer_left_append = r'(?:\<\<\<)([^\<]+)(?:\<\<\<\')'
    replacerizer_right_append = r'(?:\'\>\>\>)([^\>]+)(?:\>\>\>)'
    replacerizer_insert = r'(?:u\'\<\<\<)([^\>]+)(?:\>\>\>\')'

    final_data = '{part_1}{addition}{part_2}'.format(part_1=connector_data_part_1, addition=addition, part_2=connector_data_part_2)
    final_data = re.sub(replacerizer_wholesale, r"param['\1']", final_data)
    final_data = re.sub(replacerizer_left_append, r"' + param['\1']", final_data)
    final_data = re.sub(replacerizer_right_append, r"param['\1'] + '", final_data)
    final_data = re.sub(replacerizer_insert, r"' + param['\1'] + '", final_data)

    IMPORTANT_FILES['connector_data'] = final_data
    
    return


def collect_final_info():
    questions = [
        {
            'type': 'input',
            'name': 'app_name',
            'message': 'what do you want to call this app (do not use the same name as the existing production app name) ex: {}?'.format(
                '{} DEV'.format(IMPORTANT_FILES['metadata_data']['name'])
            ),
            'validate': lambda val: (val or '') != '' or 'a name must be provided'
        },
        {
            'type': 'input',
            'name': 'product_name',
            'message': 'what do you want to call this product (do not use the same name as the existing production product name) ex: {}?'.format(
                '{} DEV'.format(IMPORTANT_FILES['metadata_data']['product_name'])
            ),
            'validate': lambda val: (val or '') != '' or 'a product name must be provided'
        },
        {
            'type': 'input',
            'name': 'app_id',
            'message': 'what do you want to use for the app_id (do not use the same app_id as the existing production app)?',
            'validate': lambda val: (val or '') != '' or 'an app id must be provided'
        }
    ]

    answers = prompt(questions)

    IMPORTANT_FILES['metadata_data']['name'] = answers['app_name']
    IMPORTANT_FILES['metadata_data']['product_name'] = answers['product_name']
    IMPORTANT_FILES['metadata_data']['appid'] = answers['app_id']

    return


def verify():
    output('Here\'s a review', 'blue')
    output('\tdummy app name: {}'.format(IMPORTANT_FILES['metadata_data']['name']), 'cyan')
    output('\tdummy app product name: {}'.format(IMPORTANT_FILES['metadata_data']['product_name']), 'cyan')
    output('\tdummy app appid: {}'.format(IMPORTANT_FILES['metadata_data']['appid']), 'cyan')
    output('\tdummy app data files: {}'.format(', '.join([dummy_data['dummy_data_file'] for dummy_data in IMPORTANT_FILES['dummy_data']])), 'cyan')
    output('\tdummy app action overrides: {}\n'.format(', '.join([dummy_data['action_id'] for dummy_data in IMPORTANT_FILES['dummy_data']])), 'cyan')
    
    questions = [{
        'type': 'confirm',
        'name': 'are_you_sure',
        'message': 'yes, i know that\'s not everyting... but do you feel confident that this is all correct?'
    }]
    
    answer = prompt(questions)

    return answer['are_you_sure']


def create_files():

    new_name = '{}_{}'.format(
        IMPORTANT_FILES['metadata_data']['name'].lower().replace(' ', '_'),
        'dummy'
    )

    cwd = os.getcwd()
    new_dir = '{}/{}'.format(cwd[:cwd.rfind('/')], new_name)

    distutils.dir_util.copy_tree('.', new_dir)

    with open('{}/{}'.format(new_dir, IMPORTANT_FILES['connector_file']), 'w+') as connector_file:
        connector_file.write(IMPORTANT_FILES['connector_data'])

    with open('{}/{}'.format(new_dir, IMPORTANT_FILES['metadata_file']), 'w+') as metadata_file:
        metadata_file.write(json.dumps(IMPORTANT_FILES['metadata_data'], indent=4))

    for root, dirs, files in os.walk(new_dir):
        for file_name in files:
            if file_name.endswith('.py'):
                py_compile.compile('{}/{}'.format(new_dir, file_name))
    
    with tarfile.open('{}/{}.tgz'.format(cwd[:cwd.rfind('/')], new_name), mode='w:gz') as dummy_tar:
        dummy_tar.add(new_dir, arcname=new_name)

    output('congratulations! you\'re done - go try out your shiny new app', 'blue')

    return


def read_dummy_data(file_name):
    dummy_data = None

    with open(file_name, 'r') as dummy_file:
        dummy_data = dummy_file.read()
        if IMPORTANT_FILES['replacerizer_file']:
            dummy_data = replacerize(dummy_data)
        dummy_data = json.loads(dummy_data)
        if dummy_data[0].get('data') is None and dummy_data[0].get('summary') is None:
            raise Exception('critical fields missing from dummy data - must include keys "data" and "summary"')
        
    return dummy_data


def replacerize(file_data):
    for replace_value in IMPORTANT_FILES['replacerizer_data'].keys():
        file_data = file_data.replace(replace_value, IMPORTANT_FILES['replacerizer_data'][replace_value])

    return file_data


def get_confirmation(message):
    question = [
        {
            'type': 'confirm',
            'name': 'confirmed',
            'message': message
        }
    ]

    answer = prompt(question)

    return answer['confirmed']


def get_a_file(file_name):
    question = [
        {
            'type': 'input',
            'name': file_name,
            'message': '{}?'.format(file_name.replace('_', ' ')),
            'validate': file_validator
        }
    ]

    answer = prompt(question, style=style)
    IMPORTANT_FILES[file_name] = answer[file_name]

    return


@click.command()
def main():
    """ the purpose of DABCAT is to help make creating dummy apps significantly easier

    things you will need:\n
    - the source code for the app that you want to "dummy" up. you'll need all the source code, but dabcat will specifically require that you know where the *_connector.py file is and the *.json metadata file is.

    - the action identifier of the actions that you want to "dummy" up. action identifier can be found in the meta data json file of the app you're looking to "dummy" up. specifically it is the "identifier" field of a specific action (DO NOT USE THE ACTION NAME)
    
    - (optional) A "replacerizer.json" file, if you want to have DABCAT automatically replace values in your action data with other values. this feature HAS NOT BEEN TESTED... AT ALL

    at this poinnt in time you MUST launch dabcat from your app's source code directory, it will automatically find the "_connector.py" and the "*.json" metadata file. if you are using a replacerizer file, and you dropped it in the source code directory, it will find that as well (assuming you included "replacerizer" in the name).

    example:\n
    - dabcat directory : /Users/iforrest/Documents/Dev/projects/dabcat\n
    - source code directory: /Users/iforrest/Documents/Dev/projects/infoblox_dev\n
    * cd /Users/iforrest/Documents/Dev/projects/infoblox_dev\n
    * python /Users/iforrest/Documents/Dev/projects/dabcat/dabcat.py\n

    after dabcat has determined the location of your connector file, your json metadata file, and a replacerizer file, enter a prompt loop.

    after determining this dabcat will ask you for the location of your dummy data file. 

    you have two options here:
    1. you can choose to return this dummy data for a specific action regardless of parameters inputted by the end user. ex: if you are "dummy"-ing up url reputation, you can choose to return the same data regardless of the URL inputted.
    2. you can choose to return a specific set of dummy data when a specific parameter matches a value you're looking for. ex: if you are "dummy"-ing up a url reputation check, you can choose to return a specific set of dummmy data if the "url" parameter passed in, matches a specified URL.

    you can go through this loop as many times as you neeed. this will allow you to provide dummy data for multiple actions, and also for multiple values for different parameters of specific actions; e.g. maybe you want to provide dummy data for a url reptuation check against 4 distinct URLs.

    the last steps are to give your app a new name, new product name, and app id. DO NOT USE the existing names or appid for the production app or you WILL SCREW UP YOUR ENVIRONMENT.

    once all of this is complete, you'll be asked to confirm, and then dabcat will create a new folder and tarball (in the directory up from where you executed it). you can directly install the tarball in phantom."""

    cat_banner()
    output('DABCAT', 'green', figlet=True)
    output('Dummy App Builder for Code And Transforms (yes, I know it\'s a reach)\n\n', 'green')
    
    any_known = check_folder()
    if any_known:
        validate_known_data()

    get_required_data()

    try:
        read_important_files()
    except Exception as err:
        output('unable to process files, exiting DABCAT; details - {}'.format(str(err)), 'red')
        
    get_dummy_data()
    #update_documentation()
    process_data()
    collect_final_info()
    if not(verify()):
        output('i\'m so sorry this didn\'t work out - please come back and try again later', 'red')
        return
    create_files()
    
    

if __name__ == '__main__':
    main()