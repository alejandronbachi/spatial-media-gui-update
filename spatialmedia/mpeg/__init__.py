#! /usr/bin/env python

# Copyright 2016 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://apache.org
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MPEG packaging namespace router."""

__all__ = [
    "Box",
    "box",
    "constants",
    "container",
    "load",
    "mpeg4_container",
    "sa3d",
    "sv3d",
]

from spatialmedia.mpeg import box, constants, container, mpeg4_container, sa3d, sv3d
from spatialmedia.mpeg.box import Box
from spatialmedia.mpeg.mpeg4_container import load
