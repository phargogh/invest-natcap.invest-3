import sys
import os
import shutil
import readline
import argparse

import invest_natcap.testing
from invest_natcap.testing import autocomplete

#CONFIG_DATA = {
#    'Input archive': '',
#    'Output archive': '',
#}

class ConfiguredCorrectly(Exception):
    pass

def config_completer():
    autocompleter = autocomplete.Completer()
    readline.set_completer_delims(' \t\n;')
    readline.parse_and_bind('tab: complete')
    readline.set_completer(autocompleter.complete)

def _set_archive_name(keyword):
    input_archive_name = raw_input('Path to the %s : ' % keyword)

    if os.path.exists(input_archive_name):
        confirm_overwrite = raw_input('%s exists.  Overwrite? (y/n)' %
            input_archive_name)

        while confirm_overwrite not in ['y', 'n']:
            confirm_overwrite = raw_input('Confirm overwrite? (y/n)')

        if input_archive_name == 'n':
            return ''
    else:
        dirname = os.path.dirname(input_archive_name)
        if not os.path.exists(dirname):
            confirm_create_folder = raw_input(('%s does not exist.  '
                'Create path? (y/n) ') % dirname)
            while confirm_create_folder not in ['y', 'n']:
                confirm_create_folder = raw_input('Create path? (y/n)')

            if confirm_create_folder == 'y':
                os.makedirs(dirname)
    return os.path.abspath(input_archive_name)


def set_input_archive_name():
    CONFIG_DATA['Input archive']['path'] = _set_archive_name('input archive')

def set_output_archive_name():
    CONFIG_DATA['Output archive']['path'] = _set_archive_name('output archive')

def set_test_file_name():
    CONFIG_DATA['Test file']['path'] = _set_archive_name('test file')

def set_arguments_path():
    try:
        json_file = sys.argv[1]
    except IndexError:
        # When the user did not provide an arguments file
        json_file = _set_archive_name('arguments file')

    CONFIG_DATA['Arguments (in JSON)']['path'] = json_file

def finish_operation():
    completed_configs = map(lambda x: x != '',
        [data['path'] for data in CONFIG_DATA.values()])

    if False in completed_configs:
        print 'All data must be provided before finishing.'
    raise ConfiguredCorrectly()

try:
    init_json = os.path.abspath(sys.argv[1])
except IndexError:
    init_json = ''

CONFIG_DATA = {
    'Arguments (in JSON)': {
        'path': init_json,
        'function': set_arguments_path,
    },
    'Input archive': {
        'path': '',
        'function': set_input_archive_name,
    },
    'Output archive': {
        'path': '',
        'function': set_output_archive_name
    },
    'Test file': {
        'path': '',
        'function': set_test_file_name,
    },
    'Finish': {
        'path': None,
        'function': finish_operation,
    },
}

def configure_settings():
    settings = list(sorted(CONFIG_DATA.iteritems(), key=lambda x: x[0]))

    for item_no, (label, data) in enumerate(settings):
        if data['path'] == '':
            path = '(not set)'
        elif data['path'] == None:
            path = ''
        else:
            path = data['path']

        print '[%s] %-20s: %s' % (item_no, label, path)

    input_selection = raw_input('Select an item to configure: ')

    while input_selection not in map(lambda x: str(x), range(len(settings))):
        input_selection = raw_input('Input must be an option above: ')

    input_selection = int(input_selection)
    settings[input_selection][1]['function']()




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arguments', dest='arguments',
        help='JSON file with input arguments and model data')
    parser.add_argument('--input-archive', dest='input_archive',
        help='Path to where the input archive will be saved')
    parser.add_argument('--output-archive', dest='output_archive',
        help='Path to where the output archive will be saved')
    parser.add_argument('--test-file', dest='test_file',
        help='The test file to modify')

    args = parser.parse_args()

    CONFIG_DATA['Arguments (in JSON)']['path'] = args.arguments
    CONFIG_DATA['Input archive']['path'] = args.input_archive
    CONFIG_DATA['Output archive']['path'] = args.output_archive
    CONFIG_DATA['Test file']['path'] = args.test_file


    finished = False
    try:
        while not finished:
            print ''
            print ''
            configure_settings()
    except ConfiguredCorrectly:
        invest_natcap.testing.build_regression_archives(
            CONFIG_DATA['Arguments (in JSON)']['path'],
            CONFIG_DATA['Input archive']['path'],
            CONFIG_DATA['Output archive']['path'])
        print ''
        print 'Input archive saved to %s' % CONFIG_DATA['Input archive']['path']
        print 'Output archive saved to %s' % CONFIG_DATA['Output archive']['path']
    except KeyboardInterrupt:
        print "\nQuit"

if __name__ == '__main__':
    main()


#TEST_DIR = 'test'
#MANAGED_DATA = os.path.join(TEST_DIR, 'data', 'managed_data')
#MANAGED_INPUT = os.path.join(MANAGED_DATA, 'input')
#MANAGED_OUTPUT = os.path.join(MANAGED_DATA, 'output')
#
#test_file = raw_input('Test file to use: ')
#test_file = os.path.basename(test_file)
#
#test_class_name = raw_input('Name of the new test class: ')
#test_func_name = raw_input('Name of the new test_function: ')
#
#test_file = open(os.path.join(TEST_DIR, test_file), "a")
#
#input_archive = os.path.join(MANAGED_INPUT, '-'.join([test_class_name,
#    test_func_name]))
#output_archive = os.path.join(MANAGED_OUTPUT, '-'.join([test_class_name,
#    test_func_name]))
#
#invest_natcap.testing.build_regression_archives(json_file, input_archive,
#    output_archive)

#TAB = '    '
#lines_to_write = [
#    'class %s(invest_natcap.testing.GISTest):' % test_class_name,
#    '    def %s(self):' % test_func_name,
#    '        
#test_file._write(

