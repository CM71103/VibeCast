# Copyright 2026 VibeCast Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""VibeCast — AI Video Creation Agent."""

from app.agent import app as vibecast_app
from app.agent import root_agent

__all__ = ["root_agent", "vibecast_app"]
