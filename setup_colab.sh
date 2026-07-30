apt-get update -qq
pip install tqdm dnspython undetected-chromedriver webdriver-manager -q

wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -i google-chrome-stable_current_amd64.deb
apt-get install -f -y -qq
apt-get install -y -qq xvfb

pkill Xvfb || true
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99