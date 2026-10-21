#!/usr/bin/env bash
# env.sh — shared .env loader for the launchers.
#
# BudgetBuddy's configuration lives in `.env`, but an explicitly exported
# variable must WIN over the file:
#
#     ENABLE_CARDS=true ./run.sh      # has to do what it says
#
# Plain `source .env` assigns unconditionally, so it silently clobbers
# the exported value — which is exactly how `ENABLE_CARDS=true` once
# failed to reach the running Bureau.  This loader parses the file and
# exports only the variables that are NOT already set, which is the same
# rule python-dotenv uses (load_dotenv never overrides os.environ).
#
# Usage:  source ./env.sh && load_env
#
#   load_env            # load .env from the current directory
#   load_env path/file  # load a specific file

load_env() {
  local file="${1:-.env}"
  [ -f "$file" ] || return 0

  local line key val
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|'#'*) continue ;;
    esac
    line="${line#export }"
    case "$line" in
      *=*) ;;
      *) continue ;;
    esac

    key="${line%%=*}"
    val="${line#*=}"

    # trim whitespace around the key
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [ -n "$key" ] || continue

    # strip matching surrounding quotes, or a trailing " # comment"
    if [ "${#val}" -ge 2 ]; then
      if [ "${val:0:1}" = '"' ] && [ "${val: -1}" = '"' ]; then
        val="${val:1:${#val}-2}"
      elif [ "${val:0:1}" = "'" ] && [ "${val: -1}" = "'" ]; then
        val="${val:1:${#val}-2}"
      fi
    fi
    case "$val" in
      *" #"*) val="${val%% #*}" ;;
    esac

    # an already-exported variable wins over the file
    if [ -z "${!key+x}" ]; then
      export "$key=$val"
    fi
  done < "$file"
}
