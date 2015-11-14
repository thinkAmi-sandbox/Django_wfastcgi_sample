# coding: utf-8

from fabric.api import run, env, cd, prefix, execute
from fabric.network import disconnect_all
from fabric.decorators import task
import os

# デプロイ先の情報
FABRIC_HOST = "target_host_name"
FABRIC_REMOTE_USER = "fabric_access_user"
FABRIC_REMOTE_PASSWORD = "password"
FABRIC_BAT_FILE_FOR_IIS_DEFAULT_WEB_SITE = "iis_default_web_site_settings.bat"

# アプリ情報
FABRIC_BASE_DIR = r"C:\django_apps"
FABRIC_APP_DIR = os.path.join(FABRIC_BASE_DIR, r"django_wfastcgi_sample")
FABRIC_PROJECT_DIR = os.path.join(FABRIC_APP_DIR, r"my_project")

# Pythonまわりの情報
VIRTUALENV_DIR = os.path.join(FABRIC_APP_DIR, r"env")
VIRTUALENV_ACTIVATE = os.path.join(VIRTUALENV_DIR, r"Scripts\activate.bat")
PYTHON_PATH = r"c:\python34\python.exe"

# PsExecまわり
PSEXEC_DIR = r"c:\PsTools"
PSEXEC_ADMIN_USER = "Administrator"
PSEXEC_ADMIN_PASSWORD = "root"
PSEXEC_COMMAND = "PsExec.exe -u {admin} -p {password} ".format(admin=PSEXEC_ADMIN_USER, password=PSEXEC_ADMIN_PASSWORD)

# Bitbucketアカウント情報
BITBUCKET_USER = "bitbucket_user_name"
BITBUCKET_PASSWORD = "password"
BITBUCKET_REPOSITORY = "django_wfastcgi_sample"


# 警告の表示を防ぐため、以下に従い設定する
# [python - No handlers could be found for logger paramiko - Stack Overflow](http://stackoverflow.com/questions/19152578/no-handlers-could-be-found-for-logger-paramiko)
import paramiko
paramiko.util.log_to_file(r"filename.log")

# Fabricの環境設定
env.hosts = FABRIC_HOST
env.user = FABRIC_REMOTE_USER
env.password = FABRIC_REMOTE_PASSWORD
# デプロイ先のコマンドプロンプトで実行するように設定
env.shell = "Cmd.exe /C"


#------------------------------------
# Fabric Task
#------------------------------------
@task
def deploy():
    with cd(PSEXEC_DIR):
        execute(stop_iis)

    with cd(FABRIC_BASE_DIR):
		# execute()を使うと、ホスト名をキーとしたハッシュの取得となるため
		# 今回は`list_directories`を通常の関数として実行する
        dir_before_run = list_directories()
        
        if os.path.basename(FABRIC_APP_DIR) in dir_before_run:
            execute(delete_directories)

        execute(git_clone)

    with cd(FABRIC_APP_DIR):
        # virtualenvのインストール
        exists_pip = pip_list()
        if not "virtualenv" in exists_pip:
            execute(pip_install_virtualenv)
            
        # virtualenv環境の作成
        execute(create_virtualenv_environment)
        
        # virtualenv環境をactivateしてから、各種処理を実行
        with prefix(VIRTUALENV_ACTIVATE):
            # pipでrequirements.txtの内容をインストール
            execute(pip_install_by_requirements)

            # 結果確認
            execute(pip_list)

    with cd(FABRIC_PROJECT_DIR):
        with prefix(VIRTUALENV_ACTIVATE):
            # migrate実行
            execute(migrate_django)
        
    # 上記でGitリポジトリがなかった場合、初回実行時とみなしてIISの設定変更を行う
    if not os.path.basename(FABRIC_APP_DIR) in dir_before_run:
        with cd(PSEXEC_DIR):
            # ロック解除
            execute(unlock_appcmd)
        
            # wfastcgiの有効化
            with prefix(VIRTUALENV_ACTIVATE):
                execute(enable_wfastcgi)
        
            # IISのDefault Web Siteを変更
            execute(change_iis_default_web_site)

    # IISサービスの起動
    with cd(PSEXEC_DIR):
        execute(start_iis)
            
#-----------------------------------------------------------------------------
# Win32-OpenSSH用のデコレータ
# Win32-OpenSSHでは、run() を連続実行すると、
# socket.error: [Errno 10054] 既存の接続はリモート ホストに強制的に切断されました。
# というエラーが出ることから、disconnect_all()するデコレータを用意
# エラーは、`10_13_2015`と`11_09_2015`のバージョンにて確認
#-----------------------------------------------------------------------------
def disconnect(func):
    
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(**kwargs)
        
        disconnect_all()
        
        return result
    return wrapper


#-----------------------------------------------------------------------------
# IISまわり
#-----------------------------------------------------------------------------
@disconnect
def stop_iis():
    # Administratorなら止まる
    # 確認にYesと答えるため、yスイッチを使う
    # 既に停止しているときは、「cmd.exe exited with error code 2.」が返ってくる
    return run(PSEXEC_COMMAND + "net stop was /y")

def start_iis():
    run(PSEXEC_COMMAND + "net start was /y")
    disconnect_all()
    
    run(PSEXEC_COMMAND + "net start w3svc /y")
    disconnect_all()
    
    
@disconnect
def unlock_appcmd():
    return run(PSEXEC_COMMAND + r"%windir%\system32\inetsrv\appcmd unlock config -section:system.webServer/handlers")

@disconnect
def enable_wfastcgi():
    return run(PSEXEC_COMMAND + "wfastcgi-enable")
    

@disconnect
def change_iis_default_web_site():
    # バッチファイル経由で、IISのDefault Web Siteの設定を変更する
    # Fabric経由だと、ダブルコーテーションがある場合にうまく扱ってくれないため
    bat_path = os.path.join(FABRIC_APP_DIR, FABRIC_BAT_FILE_FOR_IIS_DEFAULT_WEB_SITE)
    return run(PSEXEC_COMMAND + bat_path)

#-----------------------------------------------------------------------------
# コマンドプロンプトまわり
#-----------------------------------------------------------------------------
@disconnect
def list_directories():
    results = run("dir /ad /b")
	
    # ディレクトリが改行コードで連結されて取得できているので分割する
    directories = results.splitlines()
    return directories
    
@disconnect
def delete_directories():
    return run("rd /s /q {path}".format(path=FABRIC_APP_DIR))

#-----------------------------------------------------------------------------
# Gitまわり
#-----------------------------------------------------------------------------
@disconnect
def git_clone():
    # パスワード形式での`git clone`なら通る
    return run("git clone https://{user}:{password}@bitbucket.org/{user}/{repo}.git".format(user=BITBUCKET_USER, password=BITBUCKET_PASSWORD, repo=BITBUCKET_REPOSITORY))

#-----------------------------------------------------------------------------
# Pythonまわり
#-----------------------------------------------------------------------------
@disconnect
def pip_list():
    return run("pip list")
        
@disconnect
def pip_install_virtualenv():
    return run("pip install virtualenv")

@disconnect
def pip_install_by_requirements():
    req_path = os.path.join(FABRIC_PROJECT_DIR, "requirements.txt")
    return run("pip install -r {path}".format(path=req_path))
    
@disconnect
def create_virtualenv_environment():
    return run("virtualenv -p {python_path} {env_path}".format(python_path=PYTHON_PATH, env_path=VIRTUALENV_DIR))
    
@disconnect
def migrate_django():
    return run("python manage.py migrate")
