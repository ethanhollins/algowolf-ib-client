# Use the Python3.7.2 container image
FROM python:3.7.2-stretch

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
ADD . /app

# Install the dependencies
RUN apt-get update && \
    apt-get install -y openjdk-8-jdk && \
    apt-get install -y ant && \
    apt-get clean;

# RUN curl -LO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
# RUN apt-get install -y ./google-chrome-stable_current_amd64.deb
# RUN rm google-chrome-stable_current_amd64.deb

# RUN wget -O /usr/bin/FirefoxSetup.tar.bz2 "https://download.mozilla.org/?product=firefox-latest&os=linux64"
# RUN tar xjf /usr/bin/FirefoxSetup.tar.bz2 -C /usr/bin
# RUN rm /usr/bin/FirefoxSetup.tar.bz2


# Adding trusting keys to apt for repositories
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -

# Adding Google Chrome to the repositories
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# Updating apt to see and install Google Chrome
RUN apt-get -y update

# Magic happens
RUN apt-get install -y google-chrome-stable

# Installing Unzip
RUN apt-get install -yqq unzip

# Download the Chrome Driver
RUN wget -O /tmp/chromedriver.zip http://chromedriver.storage.googleapis.com/`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE`/chromedriver_linux64.zip

# Unzip the Chrome Driver into /usr/local/bin directory
RUN unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

# Set display port as an environment variable
ENV DISPLAY=:99


RUN pip install -r requirements.txt

# RUN chmod +x /app/clientportal.beta.gw/bin/run.sh

# run the command to start Python
CMD ["python", "run.py"]