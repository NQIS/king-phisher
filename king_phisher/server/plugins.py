#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/server/plugins.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the project nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import os

from king_phisher import errors
from king_phisher import find
from king_phisher import plugins
from king_phisher.server import signals
from king_phisher.server.database import storage

class ServerPlugin(plugins.PluginBase):
	"""
	The base object to be inherited by plugins that are loaded into the King
	Phisher server. This provides a convenient interface for interacting with
	the runtime.
	"""
	_logging_prefix = 'KingPhisher.Plugins.Server.'
	def __init__(self, root_config):
		self.root_config = root_config
		"""A reference to the main server instance :py:attr:`~king_phisher.server.server.KingPhisherServer.config`."""
		self.server = None
		"""A reference to the :py:class:`~king_phisher.server.server.KingPhisherServer` instance. Only available if the instance has been created."""
		super(ServerPlugin, self).__init__()
		for option in self.options:
			if self.config[option.name] is None:
				raise errors.KingPhisherPluginError(self.name, 'missing required option: ' + option.name)
		self.storage = None
		"""
		An instance of :py:class:`~.storage.KeyValueStorage` for this plugin to
		use for persistent data storage. This attribute is None until the
		:py:obj:`~.signals.db_initialized` signal is emitted.
		"""

	@property
	def config(self):
		"""
		A dictionary that can be used by this plugin to access it's
		configuration. Any changes to this configuration will be lost with the
		server restarts.
		"""
		config = self.root_config.get('server.plugins').get(self.name)
		if config is None:
			config = {}
			self.root_config.get('server.plugins')[self.name] = config
		return config

class ServerPluginManager(plugins.PluginManagerBase):
	"""
	The manager for plugins loaded into the King Phisher server application.
	"""
	_plugin_klass = ServerPlugin
	def __init__(self, config):
		self.config = config
		path = self._get_path()
		self._server = None
		super(ServerPluginManager, self).__init__(path, (config,))
		for plugin in config.get_if_exists('server.plugins', {}).keys():
			# load the plugin
			try:
				self.load(plugin)
			except Exception:
				self.logger.critical('failed to load plugin: ' + plugin, exc_info=True)
				raise errors.KingPhisherPluginError(plugin, 'failed to load')
			# check compatibility
			klass = self[plugin]
			for req_type, req_value, req_met in klass.compatibility:
				req_type = req_type.lower()
				if req_met:
					self.logger.debug("plugin {0} requirement {1} ({2}) met".format(plugin, req_type, req_value))
					continue
				self.logger.warning("plugin {0} unmet requirement {1} ({2})".format(plugin, req_type, req_value))
				raise errors.KingPhisherPluginError(plugin, 'failed to meet requirement: ' + req_type)
			# enable the plugin
			try:
				self.enable(plugin)
			except errors.KingPhisherPluginError as error:
				raise error
			except Exception:
				self.logger.critical('failed to enable plugin: ' + plugin, exc_info=True)
				raise errors.KingPhisherPluginError(plugin, 'failed to enable')
		signals.db_initialized.connect(self._sig_db_initialized)

	def _get_path(self):
		path = [find.find_data_directory('plugins')]
		extra_dirs = self.config.get_if_exists('server.plugin_directories', [])
		if isinstance(extra_dirs, str):
			extra_dirs = [extra_dirs]
		elif not isinstance(extra_dirs, list):
			raise errors.KingPhisherInputValidationError('configuration setting server.plugin_directories must be a list')
		for directory in extra_dirs:
			if not os.path.isdir(directory):
				continue
			path.append(directory)
		return path

	def _sig_db_initialized(self, _):
		for _, plugin in self:
			plugin.storage = storage.KeyValueStorage('plugins.' + plugin.name)

	@property
	def server(self):
		return self._server

	@server.setter
	def server(self, value):
		self._server = value
		for _, plugin in self:
			plugin.server = value
