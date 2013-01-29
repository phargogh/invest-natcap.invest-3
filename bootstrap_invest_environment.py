import virtualenv, textwrap
output = virtualenv.create_bootstrap_script(textwrap.dedent("""
import os, subprocess, sys
def after_install(options, home_dir):
    print("Home dir: ", home_dir)
    print("CWD: ", os.getcwd())
    if sys.platform == 'win32':
        bin = 'Scripts'
    else:
        bin = 'bin'
    easy_install = os.path.abspath(os.path.join(home_dir, bin, 'easy_install')).replace(' ', '\ ')
    print("easy_install path: ", easy_install)
    print("easy_insall exists: ", os.path.exists(easy_install))
    subprocess.call([easy_install, 'numpy'])
    subprocess.call([easy_install, 'scipy'])
    subprocess.call([easy_install, 'nose'])
    subprocess.call([easy_install, 'setuptools'])
"""))
print output
