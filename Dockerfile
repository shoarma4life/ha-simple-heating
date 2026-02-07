ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN pip3 install --no-cache-dir requests

COPY heating_manager/ /app/heating_manager/
COPY run.sh /app/run.sh
RUN chmod a+x /app/run.sh

WORKDIR /app

CMD [ "/app/run.sh" ]
