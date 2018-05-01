FROM debian:9
LABEL author="Ayush Dwivedi"

RUN apt-get update && apt-get install -y \
    git-core \
    python-dev \
    python3-pip
RUN pip3 install \
    requests \
    schedule \
    pyyaml \
    python-dateutil

RUN apt-get update && apt-get install -y \
    supervisor \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir /var/log/supervisord /var/run/supervisord

COPY . /srv/sd-helper

CMD ["/usr/bin/supervisord", "-c", "/srv/sd-helper/supervisord.conf"]
