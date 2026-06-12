set -e

sudo apt-get update
sudo apt-get install -y python3-pip python3-flask python3-docker python3-click python3-requests
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
sudo systemctl enable docker || true
sudo systemctl start docker || sudo service docker start

cd ~/projects/faaspe
pkill -f 'platform/function.py' || true
nohup sudo -n python3 ./platform/function.py > platform.log 2>&1 &

for i in 1 2 3 4 5 6 7 8 9 10; do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/functions', timeout=1)" >/dev/null 2>&1; then
        echo "FaaSPE platform started"
        exit 0
    fi
    sleep 1
done

echo "FaaSPE platform failed to start"
tail -80 platform.log || true
exit 1
