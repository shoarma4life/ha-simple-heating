#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Simple Heating Manager..."
bashio::log.info "Check interval: $(bashio::config 'check_interval') seconds"
bashio::log.info "Log level: $(bashio::config 'log_level')"

exec python3 -m heating_manager.main
