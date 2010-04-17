# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the Gtk user interface for zim.
The main widgets and dialogs are seperated out in sub-modules.
Included here are the main class for the zim GUI, which
contains most action handlers and the main window class.

The GUI uses a few mechanisms for other classes to dynamically
add elements. One is the use of the gtk.UIManager class to
populate the menubar and toolbar. This allows other parts of
the application to define additional actions. See the methods
add_actions() and add_ui() for wrappers around this functionality.
A second mechanism is that for simple options other classes can
register a preference to be shown in the PreferencesDialog. See
the register_prererences() mmethod. NOTE: the plugin base class
has it's own wrappers for these things. Plugin writers should
look there first.

To define dialogs in the GUI please use one of the Dialog,
FileDialog, QuestionDialog or ErrorDialog classes as base class.
Especially the Dialog class contains many convenience methods to
quickly setup a simple form.
'''

import os
import logging
import gobject
import gtk

import zim
from zim import NotebookInterface, NotebookLookupError
from zim.fs import *
from zim.fs import normalize_win32_share
from zim.errors import Error
from zim.notebook import Path, Page, PageNameError, \
	resolve_default_notebook, get_notebook, get_notebook_list
from zim.stores import encode_filename
from zim.index import LINK_DIR_BACKWARD
from zim.config import data_file, config_file, data_dirs, ListDict
from zim.parsing import url_encode, URL_ENCODE_DATA, is_win32_share_re
from zim.history import History, HistoryRecord
from zim.gui.pathbar import NamespacePathBar, RecentPathBar, HistoryPathBar
from zim.gui.pageindex import PageIndex
from zim.gui.pageview import PageView
from zim.gui.widgets import Button, MenuButton, \
	Dialog, ErrorDialog, QuestionDialog, FileDialog, ProgressBarDialog
from zim.gui.clipboard import Clipboard
from zim.gui.applications import get_application, CustomToolManager

logger = logging.getLogger('zim.gui')

ui_actions = (
	('file_menu', None, _('_File')), # T: Menu title
	('edit_menu', None, _('_Edit')), # T: Menu title
	('view_menu', None, _('_View')), # T: Menu title
	('insert_menu', None, _('_Insert')), # T: Menu title
	('search_menu', None, _('_Search')), # T: Menu title
	('format_menu', None, _('For_mat')), # T: Menu title
	('tools_menu', None, _('_Tools')), # T: Menu title
	('go_menu', None, _('_Go')), # T: Menu title
	('help_menu', None, _('_Help')), # T: Menu title
	('pathbar_menu', None, _('P_athbar')), # T: Menu title
	('toolbar_menu', None, _('_Toolbar')), # T: Menu title

	# name, stock id, label, accelerator, tooltip, readonly
	('new_page',  'gtk-new', _('_New Page...'), '<ctrl>N', '', False), # T: Menu item
	('new_sub_page',  'gtk-new', _('New S_ub Page...'), '', '', False), # T: Menu item
	('open_notebook', 'gtk-open', _('_Open Another Notebook...'), '<ctrl>O', '', True), # T: Menu item
	('open_new_window', None, _('Open in New _Window'), '', '', True), # T: Menu item
	('import_page', None, _('_Import Page...'), '', '', False), # T: Menu item
	('save_page', 'gtk-save', _('_Save'), '<ctrl>S', '', False), # T: Menu item
	('save_copy', None, _('Save A _Copy...'), '', '', True), # T: Menu item
	('show_export',  None, _('E_xport...'), '', '', True), # T: Menu item
	('email_page', None, _('_Send To...'), '', '', True), # T: Menu item
	('move_page', None, _('_Move Page...'), '', '', False), # T: Menu item
	('rename_page', None, _('_Rename Page...'), 'F2', '', False), # T: Menu item
	('delete_page', None, _('_Delete Page'), '', '', False), # T: Menu item
	('show_properties',  'gtk-properties', _('Proper_ties'), '', '', True), # T: Menu item
	('close',  'gtk-close', _('_Close'), '<ctrl>W', '', True), # T: Menu item
	('quit',  'gtk-quit', _('_Quit'), '<ctrl>Q', '', True), # T: Menu item
	('show_search',  'gtk-find', _('_Search...'), '<shift><ctrl>F', '', True), # T: Menu item
	('show_search_backlinks', None, _('Search _Backlinks...'), '', '', True), # T: Menu item
	('copy_location', None, _('Copy Location'), '<shift><ctrl>L', '', True), # T: Menu item
	('show_preferences',  'gtk-preferences', _('Pr_eferences'), '', '', True), # T: Menu item
	('reload_page',  'gtk-refresh', _('_Reload'), '<ctrl>R', '', True), # T: Menu item
	('open_attachments_folder', 'gtk-open', _('Open Attachments _Folder'), '', '', True), # T: Menu item
	('open_notebook_folder', 'gtk-open', _('Open _Notebook Folder'), '', '', True), # T: Menu item
	('open_document_root', 'gtk-open', _('Open _Document Root'), '', '', True), # T: Menu item
	('open_document_folder', 'gtk-open', _('Open _Document Folder'), '', '', True), # T: Menu item
	('attach_file', 'zim-attachment', _('Attach _File'), '', _('Attach external file'), False), # T: Menu item
	('edit_page_source', 'gtk-edit', _('Edit _Source'), '', '', False), # T: Menu item
	('show_server_gui', None, _('Start _Web Server'), '', '', True), # T: Menu item
	('reload_index', None, _('Re-build Index'), '', '', False), # T: Menu item
	('manage_custom_tools', 'gtk-preferences', _('Custom _Tools'), '', '', True), # T: Menu item
	('open_page_back', 'gtk-go-back', _('_Back'), '<alt>Left', _('Go page back'), True), # T: Menu item
	('open_page_forward', 'gtk-go-forward', _('_Forward'), '<alt>Right', _('Go page forward'), True), # T: Menu item
	('open_page_parent', 'gtk-go-up', _('_Parent'), '<alt>Up', _('Go to parent page'), True), # T: Menu item
	('open_page_child', 'gtk-go-down', _('_Child'), '<alt>Down', _('Go to child page'), True), # T: Menu item
	('open_page_previous', None, _('_Previous in index'), '<alt>Page_Up', _('Go to previous page'), True), # T: Menu item
	('open_page_next', None, _('_Next in index'), '<alt>Page_Down', _('Go to next page'), True), # T: Menu item
	('open_page_home', 'gtk-home', _('_Home'), '<alt>Home', _('Go home'), True), # T: Menu item
	('open_page', 'gtk-jump-to', _('_Jump To...'), '<ctrl>J', '', True), # T: Menu item
	('show_help', 'gtk-help', _('_Contents'), 'F1', '', True), # T: Menu item
	('show_help_faq', None, _('_FAQ'), '', '', True), # T: Menu item
	('show_help_keys', None, _('_Keybindings'), '', '', True), # T: Menu item
	('show_help_bugs', None, _('_Bugs'), '', '', True), # T: Menu item
	('show_about', 'gtk-about', _('_About'), '', '', True), # T: Menu item
)

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, initial state, readonly
	('toggle_toolbar', None, _('_Toolbar'),  None, '', True, True), # T: Menu item
	('toggle_statusbar', None, _('_Statusbar'), None, '', True, True), # T: Menu item
	('toggle_sidepane',  'gtk-index', _('_Index'), 'F9', _('Show index'), True, True), # T: Menu item
	('toggle_fullscreen',  None, _('_Fullscreen'), 'F11', '', False, True), # T: Menu item
	('toggle_readonly', 'gtk-edit', _('Notebook _Editable'), '', _('Toggle notebook editable'), True, True), # T: menu item
)

ui_pathbar_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_pathbar_none', None, _('_None'),  None, None, 0), # T: Menu item
	('set_pathbar_recent', None, _('_Recent pages'), None, None, 1), # T: Menu item
	('set_pathbar_history', None, _('_History'),  None, None, 2), # T: Menu item
	('set_pathbar_path', None, _('N_amespace'), None, None, 3), # T: Menu item
)

PATHBAR_NONE = 'none'
PATHBAR_RECENT = 'recent'
PATHBAR_HISTORY = 'history'
PATHBAR_PATH = 'path'

ui_toolbar_style_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_and_text', None, _('Icons _And Text'), None, None, 0), # T: Menu item
	('set_toolbar_icons_only', None, _('_Icons Only'), None, None, 1), # T: Menu item
	('set_toolbar_text_only', None, _('_Text Only'), None, None, 2), # T: Menu item
)

ui_toolbar_size_radio_actions = (
	# name, stock id, label, accelerator, tooltip
	('set_toolbar_icons_large', None, _('_Large Icons'), None, None, 0), # T: Menu item
	('set_toolbar_icons_small', None, _('_Small Icons'), None, None, 1), # T: Menu item
	('set_toolbar_icons_tiny', None, _('_Tiny Icons'), None, None, 2), # T: Menu item
)

TOOLBAR_ICONS_AND_TEXT = 'icons_and_text'
TOOLBAR_ICONS_ONLY = 'icons_only'
TOOLBAR_TEXT_ONLY = 'text_only'

TOOLBAR_ICONS_LARGE = 'large'
TOOLBAR_ICONS_SMALL = 'small'
TOOLBAR_ICONS_TINY = 'tiny'

ui_preferences = (
	# key, type, category, label, default
	('tearoff_menus', 'bool', 'Interface', _('Add \'tearoff\' strips to the menus'), False),
		# T: Option in the preferences dialog
	('toggle_on_ctrlspace', 'bool', 'Interface', _('Use <Ctrl><Space> to switch to the side pane\n(If disabled you can still use <Alt><Space>)'), False),
		# T: Option in the preferences dialog
		# default value is False because this is mapped to switch between
		# char sets in cerain international key mappings
)


# Load custom application icons as stock
def load_zim_stock_icons():
	factory = gtk.IconFactory()
	factory.add_default()
	for dir in data_dirs(('pixmaps')):
		for file in dir.list():
			if not file.endswith('.png'):
				continue # no all installs have svg support..
			name = 'zim-'+file[:-4] # e.g. checked-box.png -> zim-checked-box
			try:
				pixbuf = gtk.gdk.pixbuf_new_from_file(str(dir+file))
				set = gtk.IconSet(pixbuf=pixbuf)
				factory.add(name, set)
			except Exception:
				logger.exception('Got exception while loading application icons')

load_zim_stock_icons()


KEYVAL_ESC = gtk.gdk.keyval_from_name('Escape')


def schedule_on_idle(function, args=()):
	'''Helper function to schedule stuff that can be done later'''
	def callback():
		function(*args)
		return False # delete signal
	gobject.idle_add(callback)


class NoSuchFileError(Error):

	description = _('The file or folder you specified does not exist.\nPlease check if you the path is correct.')
		# T: Error description for "no such file or folder"

	def __init__(self, path):
		self.msg = _('No such file or folder: %s') % path.path
			# T: Error message, %s will be the file path


class RLock(object):
	'''Kind of re-entrant lock that keeps a stack count'''

	__slots__ = ('count',)

	def __init__(self):
		self.count = 0

	def __nonzero__(self):
		return self.count > 0

	def increment(self):
		self.count += 1

	def decrement(self):
		if self.count == 0:
			raise AssertionError, 'BUG: RLock count can not go below zero'
		self.count -= 1


class GtkInterface(NotebookInterface):
	'''Main class for the zim Gtk interface. This object wraps a single
	notebook and provides actions to manipulate and access this notebook.

	Signals:
	* open-page (page, path)
	  Called when opening another page, see open_page() for details
	* close-page (page)
	  Called when closing a page, typically just before a new page is opened
	  and before closing the application
	* preferences-changed
	  Emitted after the user changed the preferences
	  (typically triggered by the preferences dialog)
	* read-only-changed
	  Emitted when the ui changed from read-write to read-only or back
	* quit
	  Emitted when the application is about to quit

	Also see signals in zim.NotebookInterface
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'close-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'preferences-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'readonly-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'quit': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	ui_type = 'gtk'

	def __init__(self, notebook=None, page=None,
		fullscreen=False, geometry=None, usedaemon=False):
		assert not (page and notebook is None), 'BUG: can not give page while notebook is None'
		NotebookInterface.__init__(self)
		self.preferences_register = ListDict()
		self.page = None
		self.history = None
		self._autosave_lock = RLock()
			# used to prevent autosave triggering while we are
			# doing a (async) save, or when we have an error during
			# saving.
		self.readonly = False
		self.usedaemon = usedaemon
		self.hideonclose = False

		logger.debug('Gtk version is %s' % str(gtk.gtk_version))
		logger.debug('Pygtk version is %s' % str(gtk.pygtk_version))

		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

		self.uimanager = gtk.UIManager()
		self.uimanager.add_ui_from_string('''
		<ui>
			<menubar name="menubar">
			</menubar>
			<toolbar name="toolbar">
			</toolbar>
		</ui>
		''')

		self.register_preferences('GtkInterface', ui_preferences)

		# Hidden setting to force the gtk bell off. Otherwise it
		# can bell every time you reach the begin or end of the text
		# buffer. Especially specific gtk version on windows.
		# See bug lp:546920
		self.preferences['GtkInterface'].setdefault('gtk_bell', False)
		if not self.preferences['GtkInterface']['gtk_bell']:
			gtk.rc_parse_string('gtk-error-bell = 0')

		# Set default applications
		apps = {
			'email_client': ['xdg-email', 'startfile'],
			'file_browser': ['xdg-open', 'startfile'],
			'web_browser': ['xdg-open', 'startfile']
		}
		for type in apps.keys():
			prefs = self.preferences['GtkInterface']
			if type in prefs and prefs[type] \
			and isinstance(prefs[type], basestring):
				pass # preference is set, no need to set default
			else:
				from zim.gui.applications import get_helper_applications
				key = None
				helpers = get_helper_applications(type)
				keys = [entry.key for entry in helpers]
				for k in apps[type]: # prefered keys
					if k in keys:
						key = k
						break
				if key is None:
					if helpers: key = helpers[0].key
					else: key = 'none'
				prefs.setdefault(type, key)

		self.mainwindow = MainWindow(self, fullscreen, geometry)

		self.add_actions(ui_actions, self)
		self.add_toggle_actions(ui_toggle_actions, self.mainwindow)
		self.add_radio_actions(ui_pathbar_radio_actions,
								self.mainwindow, 'do_set_pathbar')
		self.add_radio_actions(ui_toolbar_style_radio_actions,
								self.mainwindow, 'do_set_toolbar_style')
		self.add_radio_actions(ui_toolbar_size_radio_actions,
								self.mainwindow, 'do_set_toolbar_size')
		self.add_ui(data_file('menubar.xml').read(), self)

		self.load_plugins()

		self._custom_tool_ui_id = None
		self._custom_tool_actiongroup = None
		self.load_custom_tools()

		self.uimanager.ensure_update()
			# prevent flashing when the toolbar is after showing the window
			# and do this before connecting signal below for accelmap

		accelmap = config_file('accelmap').file
		logger.debug('Accelmap: %s', accelmap.path)
		if accelmap.exists():
			gtk.accel_map_load(accelmap.path)

		def on_accel_map_changed(o, path, key, mod):
			logger.info('Accelerator changed for %s', path)
			gtk.accel_map_save(accelmap.path)

		gtk.accel_map_get().connect('changed', on_accel_map_changed)

		self.do_preferences_changed()

		# Deal with commandline arguments for notebook and page
		if notebook:
			self.open_notebook(notebook)
			if self.notebook is None:
				# Exit the program before reaching main()
				raise Exception, 'Could not open notebook: %s' % notebook

			if page:
				if isinstance(page, basestring):
					page = self.notebook.resolve_path(page)
					if not page is None:
						self.open_page(page)
				else:
					assert isinstance(page, Path)
					self.open_page(page)
		else:
			pass # Will check default in main()

	def spawn(self, *args):
		if not self.usedaemon:
			args = args + ('--no-daemon',)
		NotebookInterface.spawn(self, *args)

	def main(self):
		'''Wrapper for gtk.main(); does not return untill program has ended.'''
		if self.notebook is None:
			import zim.gui.notebookdialog
			notebook = zim.gui.notebookdialog.prompt_notebook()
			if notebook:
				self.open_notebook(notebook)
			else:
				# User cancelled notebook dialog
				return

		if self.notebook.dir:
			os.chdir(self.notebook.dir.path)
			os.environ['PWD'] = self.notebook.dir.path

		if self.page is None:
			path = self.history.get_current()
			if path:
				self.open_page(path)
			else:
				self.open_page_home()

		# We schedule the autosave on idle to try to make it impact
		# the performance of the applciation less. Of course using the
		# async interface also helps, but we need to account for cases
		# where asynchronous actions are not supported.

		def autosave():
			page = self.mainwindow.pageview.get_page()
			if page.modified and not self._autosave_lock:
					self.save_page_async(page)

		def schedule_autosave():
			schedule_on_idle(autosave)
			return True # keep ticking

		# older gobject version doesn't know about seconds
		self._autosave_timer = gobject.timeout_add(5000, schedule_autosave)

		for plugin in self.plugins:
			plugin.finalize_ui(self)

		self.check_notebook_needs_upgrade()

		self.mainwindow.show_all()
		self.mainwindow.pageview.grab_focus()
		gtk.main()

	def present(self, page=None, fullscreen=None, geometry=None):
		'''Present a specific page the main window and/or set window mode'''
		self.mainwindow.present()
		if page:
			if isinstance(page, basestring):
				page = Path(page)
			self.open_page(page)

		if geometry:
			self.mainwindow.parse_geometry(geometry)
		elif fullscreen:
			self.mainwindow.toggle_fullscreen(show=True)

	def toggle_present(self):
		'''Present main window if it is not on top, but hide if it is.
		Used by the TrayIcon to toggle visibility of the window.
		'''
		if self.mainwindow.is_active():
			self.mainwindow.hide()
		else:
			self.mainwindow.present()

	def hide(self):
		'''Hide the main window (this is not the same as minimize)'''
		self.mainwindow.hide()

	def close(self):
		if self.hideonclose:
			self.hide()
		else:
			self.quit()

	def quit(self):
		# TODO: logic to hide the window
		if not self.close_page(self.page):
			# Do not quit if page not saved
			return

		self.emit('quit')

		if self.uistate.modified:
			self.uistate.write()

		self.mainwindow.destroy()
		gtk.main_quit()

	def add_actions(self, actions, handler, methodname=None):
		'''Wrapper for gtk.ActionGroup.add_actions(actions),
		"handler" is the object that has the methods for these actions.

		Each action is mapped to a like named method of the handler
		object. If the object not yet has an actiongroup this is created first,
		attached to the uimanager and put in the "actiongroup" attribute.
		'''
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tupels'
		group = self.init_actiongroup(handler)
		group.add_actions([a[0:5] for a in actions])
		self._connect_actions(actions, group, handler)

	def add_toggle_actions(self, actions, handler):
		'''Wrapper for gtk.ActionGroup.add_toggle_actions(actions),
		"handler" is the object that has the methods for these actions.

		Differs for add-actions() in that in the mapping from action name
		to method name is prefixed with "do_". The reason for this is that
		in order to keep the state of toolbar and menubar widgets stays in
		sync with the internal state. Therefore the method of the same name
		as the action should just call activate() on the action, while the
		actual logic is implamented in the handler which is prefixed with
		"do_".
		'''
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tupels'
		group = self.init_actiongroup(handler)
		group.add_toggle_actions([a[0:5]+(None,)+(a[5],) for a in actions])
			# insert 'None' for callback
		self._connect_actions(actions, group, handler, is_toggle=True)

	def init_actiongroup(self, handler):
		'''Initializes the actiongroup for 'handler' if it does not already
		exist and returns the actiongroup.
		'''
		if not hasattr(handler, 'actiongroup') or handler.actiongroup is None:
			name = handler.__class__.__name__
			handler.actiongroup = gtk.ActionGroup(name)
			self.uimanager.insert_action_group(handler.actiongroup, 0)
		return handler.actiongroup

	def remove_actiongroup(self, handler):
		'''Remove the actiongroup for 'handler' and thereby all actions'''
		if hasattr(handler, 'actiongroup') and handler.actiongroup:
			self.uimanager.remove_action_group(handler.actiongroup)
			handler.actiongroup = None

	@staticmethod
	def _log_action(action, *a):
		logger.debug('Action: %s', action.get_name())

	def _connect_actions(self, actions, group, handler, is_toggle=False):
		for name, readonly in [(a[0], a[-1]) for a in actions if not a[0].endswith('_menu')]:
			action = group.get_action(name)
			action.zim_readonly = readonly
			if is_toggle: name = 'do_' + name
			assert hasattr(handler, name), 'No method defined for action %s' % name
			method = getattr(handler.__class__, name)
			action.connect('activate', self._log_action)
			action.connect_object('activate', method, handler)
			if self.readonly and not action.zim_readonly:
				action.set_sensitive(False)

	def add_radio_actions(self, actions, handler, methodname):
		'''Wrapper for gtk.ActionGroup.add_radio_actions(actions),
		"handler" is the object that these actions belong to and
		"methodname" gives the callback to be called on changes in this group.
		(See doc on gtk.RadioAction 'changed' signal for this callback.)
		'''
		# A bit different from the other two methods since radioactions
		# come in mutual exclusive groups. Only need to connect to one
		# action to get signals from whole group.
		assert isinstance(actions[0], tuple), 'BUG: actions should be list of tupels'
		assert hasattr(handler, methodname), 'No such method %s' % methodname
		group = self.init_actiongroup(handler)
		group.add_radio_actions(actions)
		method = getattr(handler.__class__, methodname)
		action = group.get_action(actions[0][0])
		action.connect('changed', self._log_action)
		action.connect_object('changed', method, handler)

	def add_ui(self, xml, handler):
		'''Wrapper for gtk.UIManager.add_ui_from_string(xml)'''
		id = self.uimanager.add_ui_from_string(xml)
		if hasattr(handler, '_ui_merge_ids') and handler._ui_merge_ids:
			handler._ui_merge_ids += (id,)
		else:
			handler._ui_merge_ids = (id,)
		return id

	def remove_ui(self, handler, id=None):
		'''Remove the ui definition(s) for a specific handler. If an id is
		given, only removes that ui part, else removes all ui parts defined
		for this handler.
		'''
		if id:
			self.uimanager.remove_ui(id)
			if hasattr(handler, '_ui_merge_ids'):
				handler._ui_merge_ids = \
					filter(lambda i: i != id, handler._ui_merge_ids)
		else:
			if hasattr(handler, '_ui_merge_ids'):
				for id in handler._ui_merge_ids:
					self.uimanager.remove_ui(id)
				handler._ui_merge_ids = None

	def set_readonly(self, readonly):
		if not self.readonly:
			# Save any modification now - will not be allowed after switch
			page = self.mainwindow.pageview.get_page()
			if page and page.modified:
				self.save_page(page)

		for group in self.uimanager.get_action_groups():
			for action in group.list_actions():
				if hasattr(action, 'zim_readonly') \
				and not action.zim_readonly:
					action.set_sensitive(not readonly)

		self.readonly = readonly
		self.emit('readonly-changed')

	def register_preferences(self, section, preferences):
		'''Registers user preferences. Registering means that a
		preference will show up in the preferences dialog.
		The section given is the section to locate these preferences in the
		config file. Each preference is a tuple consisting of:

		* the key in the config file
		* an option type (see Dialog.add_fields() for more details)
		* a category (the tab in which the option will be shown)
		* a label to show in the dialog
		* a default value
		'''
		register = self.preferences_register
		for p in preferences:
			key, type, category, label, default = p
			self.preferences[section].setdefault(key, default)
			register.setdefault(category, [])
			register[category].append((section, key, type, label))

	def get_path_context(self):
		'''Returns the current 'context' for actions that want a path to start
		with. Asks the mainwindow for a selected page, defaults to the
		current page if any.
		'''
		return self.mainwindow.get_selected_path() or self.page

	def open_notebook(self, notebook=None):
		'''Open a new notebook. If this is the first notebook the open-notebook
		signal is emitted and the notebook is opened in this process. Otherwise
		we let another instance handle it. If notebook=None the notebookdialog
		is run to prompt the user.'''
		if not self.notebook:
			assert not notebook is None, 'BUG: first initialize notebook'
			try:
				page = NotebookInterface.open_notebook(self, notebook)
			except NotebookLookupError, error:
				ErrorDialog(self, error).run()
			else:
				if page:
					self.open_page(page)
		elif notebook is None:
			# Handle menu item for 'open another notebook'
			from zim.gui.notebookdialog import NotebookDialog
			NotebookDialog.unique(self, self, callback=self.open_notebook).show() # implicit recurs
		else:
			# Could be call back from open notebook dialog
			# We are already intialized, so let another process handle it
			if self.usedaemon:
				from zim.daemon import DaemonProxy
				notebook = DaemonProxy().get_notebook(notebook)
				notebook.present()
			else:
				self.spawn(notebook)

	def do_open_notebook(self, notebook):
		'''Signal handler for open-notebook.'''

		def move_away(o, path):
			if path == self.page or self.page.ischild(path):
				self.open_page_back() \
				or self.open_page_parent \
				or self.open_page_home

		def follow(o, path, newpath, update_links):
			if self.page == path:
				self.open_page(newpath)
			elif self.page.ischild(path):
				newpath = newpath + self.page.relname(path)
				newpath = Path(newpath.name) # IndexPath -> Path
				self.open_page(newpath)

		def autosave(o, p, *a):
			# Here we explicitly do not save async
			# and also explicitly no need for _autosave_lock
			page = self.mainwindow.pageview.get_page()
			if p == page and page.modified:
				self.save_page(page)

		NotebookInterface.do_open_notebook(self, notebook)
		self.history = History(notebook, self.uistate)
		self.on_notebook_properties_changed(notebook)
		notebook.connect('properties-changed', self.on_notebook_properties_changed)
		notebook.connect('delete-page', autosave) # before action
		notebook.connect('move-page', autosave) # before action
		notebook.connect('deleted-page', move_away)
		notebook.connect('moved-page', follow)

		# Start a lightweight background check of the index
		self.notebook.index.update(background=True, checkcontents=False)

		self.set_readonly(notebook.readonly)

	def check_notebook_needs_upgrade(self):
		if not self.notebook.needs_upgrade:
			return

		ok = QuestionDialog(None, (
			_('Upgrade Notebook?'), # T: Short question for question prompt
			_('This notebook was created by an older of version of zim.\n'
			  'Do you want to upgrade it to the latest version now?\n\n'
			  'Upgrading will take some time and may make various changes\n'
			  'to the notebook. In general it is a good idea to make a\n'
			  'backup before doing this.\n\n'
			  'If you choose not to upgrade now, some features\n'
			  'may not work as expected') # T: Explanation for question to upgrade notebook
		) ).run()

		if not ok:
			return

		dialog = ProgressBarDialog(self, _('Upgrading notebook'))
			# T: Title of progressbar dialog
		dialog.show_all()
		self.notebook.index.ensure_update(callback=lambda p: dialog.pulse(p.name))
		dialog.set_total(self.notebook.index.n_all_pages())
		self.notebook.upgrade_notebook(callback=lambda p: dialog.pulse(p.name))
		dialog.destroy()

	def on_notebook_properties_changed(self, notebook):
		has_doc_root = not notebook.get_document_root() is None
		for action in ('open_document_root', 'open_document_folder'):
			action = self.actiongroup.get_action(action)
			action.set_sensitive(has_doc_root)

	def open_page(self, path=None):
		'''Emit the open-page signal. The argument 'path' can either be a Page
		or a Path object. If 'page' is None a dialog is shown
		to specify the page. If 'path' is a HistoryRecord we assume that this
		call is the result of a history action and the page is not added to
		the history. The original path object is given as the second argument
		in the signal, so handlers can inspect how this method was called.
		'''
		assert self.notebook
		if path is None:
			# the dialog will call us in turn with an argument
			return OpenPageDialog(self).run()

		assert isinstance(path, Path)
		if isinstance(path, Page) and path.valid:
			page = path
		else:
			page = self.notebook.get_page(path)

		if self.page and id(self.page) == id(page):
			# Check ID to enable reload_page but catch all other
			# redundant calls.
			return
		elif self.page:
			if not self.close_page(self.page):
				raise AssertionError, 'Could not close page'
				# assert statement could be optimized away

		logger.info('Open page: %s (%s)', page, path)
		self.emit('open-page', page, path)

	def do_open_page(self, page, path):
		'''Signal handler for open-page.'''
		is_first_page = self.page is None
		self.page = page

		back = self.actiongroup.get_action('open_page_back')
		forward = self.actiongroup.get_action('open_page_forward')
		parent = self.actiongroup.get_action('open_page_parent')
		child = self.actiongroup.get_action('open_page_child')

		if isinstance(path, HistoryRecord):
			historyrecord = path
			self.history.set_current(path)
			back.set_sensitive(not path.is_first)
			forward.set_sensitive(not path.is_last)
		else:
			self.history.append(page)
			historyrecord = self.history.get_current()
			back.set_sensitive(not is_first_page)
			forward.set_sensitive(False)

		if historyrecord and not historyrecord.cursor == None:
			self.mainwindow.pageview.set_cursor_pos(historyrecord.cursor)
			self.mainwindow.pageview.set_scroll_pos(historyrecord.scroll)


		parent.set_sensitive(len(page.namespace) > 0)
		child.set_sensitive(page.haschildren)

	def close_page(self, page=None):
		'''Emits the 'close-page' signal and returns boolean for success'''
		if page is None:
			page = self.page
		self.emit('close-page', page)
		return not page.modified

	def do_close_page(self, page):
		if page.modified:
			self.save_page(page) # No async here -- for now

		current = self.history.get_current()
		if current == page:
			current.cursor = self.mainwindow.pageview.get_cursor_pos()
			current.scroll = self.mainwindow.pageview.get_scroll_pos()

		if self.uistate.modified:
			schedule_on_idle(self.uistate.write_async)

	def open_page_back(self):
		record = self.history.get_previous()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_forward(self):
		record = self.history.get_next()
		if not record is None:
			self.open_page(record)
			return True
		else:
			return False

	def open_page_parent(self):
		namespace = self.page.namespace
		if namespace:
			self.open_page(Path(namespace))
			return True
		else:
			return False

	def open_page_child(self):
		if not self.page.haschildren:
			return False

		record = self.history.get_child(self.page)
		if not record is None:
			self.open_page(record)
		else:
			pages = list(self.notebook.index.list_pages(self.page))
			self.open_page(pages[0])
		return True

	def open_page_previous(self):
		path = self.notebook.index.get_previous(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_next(self):
		path = self.notebook.index.get_next(self.page)
		if not path is None:
			self.open_page(path)
			return True
		else:
			return False

	def open_page_home(self):
		self.open_page(self.notebook.get_home_page())

	def new_page(self):
		'''opens a dialog like 'open_page(None)'. Subtle difference is
		that this page is saved directly, so it is pesistent if the user
		navigates away without first adding content. Though subtle this
		is expected behavior for users not yet fully aware of the automatic
		create/save/delete behavior in zim.
		'''
		NewPageDialog(self).run()

	def new_sub_page(self):
		'''Same as new_page() but sets the namespace widget one level deeper'''
		NewPageDialog(self, path=self.get_path_context(), subpage=True).run()

	def new_page_from_text(self, text, name=None):
		if not name:
			name = text.strip()[:30]
			if '\n' in name:
				name, _ = name.split('\n', 1)
			name = self.notebook.cleanup_pathname(
				name.replace(':', ''), purge=True)
		path = self.notebook.resolve_path(name)
		page = self.notebook.get_new_page(path)
		page.parse('plain', text)
		self.notebook.store_page(page)
		self.open_page(page)

	def open_new_window(self, page=None):
		'''Open page in a new window'''
		if page is None:
			page = self.get_path_context()
		PageWindow(self, page).show_all()

	def save_page(self, page=None):
		'''Save 'page', or current page when 'page' is None.
		Returns boolean for success.
		'''
		page = self._save_page_check_page(page)
		if page is None:
			return

		logger.debug('Saving page: %s', page)
		try:
			self.notebook.store_page(page)
		except Exception, error:
			logger.exception('Failed to save page: %s', page.name)
			self._autosave_lock.increment()
				# We need this flag to prevent autosave trigger while we
				# are showing the SavePageErrorDialog
			SavePageErrorDialog(self, error, page).run()
			self._autosave_lock.decrement()

		return not page.modified

	def save_page_async(self, page=None):
		page = self._save_page_check_page(page)
		if page is None:
			return

		logger.debug('Saving page (async): %s', page)

		def callback(ok, error, exc_info, name):
			# This callback is called back here in the main thread.
			# We fetch the page again just to be sure in case of strange
			# edge cases. The SavePageErrorDialog will just take the
			# current state of the page, not the state that it had in
			# the async thread. This is done on purpose, current state
			# is what the user is concerned with anyway.
			#~ print '!!', ok, exc_info, name
			if exc_info:
				page = self.notebook.get_page(Path(name))
				logger.error('Failed to save page: %s', page.name, exc_info=exc_info)
				SavePageErrorDialog(self, error, page).run()
			self._autosave_lock.decrement()

		self._autosave_lock.increment()
			# Prevent any new auto save to be scheduled while we are
			# still busy with this call.
		self.notebook.store_page_async(page, callback=callback, data=page.name)

	def _save_page_check_page(self, page):
		# Code shared between save_page() and save_page_async()
		try:
			assert not self.readonly, 'BUG: can not save page when read-only'
			if page is None:
				page = self.mainwindow.pageview.get_page()
			assert not page.readonly, 'BUG: can not save read-only page'
		except Exception, error:
			SavePageErrorDialog(self, error, page).run()
			return None
		else:
			return page

	def save_copy(self):
		'''Offer to save a copy of a page in the source format, so it can be
		imported again later. Subtly different from export.
		'''
		SaveCopyDialog(self).run()

	def show_export(self):
		from zim.gui.exportdialog import ExportDialog
		ExportDialog(self).run()

	def email_page(self):
		text = ''.join(self.page.dump(format='plain'))
		url = 'mailto:?subject=%s&body=%s' % (
			url_encode(self.page.name, mode=URL_ENCODE_DATA),
			url_encode(text, mode=URL_ENCODE_DATA),
		)
		self.open_url(url)

	def import_page(self):
		'''Import a file from outside the notebook as a new page.'''
		ImportPageDialog(self).run()

	def move_page(self, path=None):
		'''Prompt dialog for moving a page'''
		MovePageDialog(self, path=path).run()

	def do_move_page(self, path, newpath, update_links):
		'''Callback for MovePageDialog and PageIndex for executing
		notebook.move_page but wrapping with all the proper exception
		dialogs. Returns boolean for success.
		'''
		return self._wrap_move_page(
			lambda update_links, callback: self.notebook.move_page(
				path, newpath, update_links, callback),
			update_links
		)

	def rename_page(self, path=None):
		'''Prompt a dialog for renaming a page'''
		RenamePageDialog(self, path=path).run()

	def do_rename_page(self, path, newbasename, update_heading=True, update_links=True):
		'''Callback for RenamePageDialog for executing
		notebook.rename_page but wrapping with all the proper exception
		dialogs. Returns boolean for success.
		'''
		return self._wrap_move_page(
			lambda update_links, callback: self.notebook.rename_page(
				path, newbasename, update_heading, update_links, callback),
			update_links
		)

	def _wrap_move_page(self, func, update_links):
		if self.notebook.index.updating:
			# Ask regardless of update_links because it might very
			# well be that the dialog thinks there are no links
			# but they are simply not indexed yet
			cont = QuestionDialog(dialog or self,
				_('The index is still busy updating. Untill this'
				  'is finished links can not be updated correctly.'
				  'Performing this action now could break links,'
				  'do you want to continue anyway?'
				) # T: question dialog text
			).run()
			if cont:
				update_links = False
			else:
				return False

		dialog = ProgressBarDialog(self, _('Updating Links'))
			# T: Title of progressbar dialog
		dialog.show_all()
		callback = lambda p, **kwarg: dialog.pulse(p.name, **kwarg)

		try:
			func(update_links, callback)
		except Exception, error:
			ErrorDialog(self, error).run()
			dialog.destroy()
			return False
		else:
			dialog.destroy()
			return True

	def delete_page(self, path=None):
		if path is None:
			path = self.get_path_context()

		page = self.notebook.get_page(path)
		if page.hascontent or page.haschildren:
			DeletePageDialog(self, path=page).run()
		else:
			ErrorDialog(self, (
				_('Page does not exist'), # T: short error description
				_('This page does not exist, so it can not be deleted')
					# T: long error description
			) ).run()

	def show_properties(self):
		from zim.gui.propertiesdialog import PropertiesDialog
		PropertiesDialog(self).run()

	def show_search(self, query=None):
		from zim.gui.searchdialog import SearchDialog
		SearchDialog(self, query).show_all()

	def show_search_backlinks(self):
		query = 'LinksTo: "%s"' % self.page.name
		self.show_search(query)

	def copy_location(self):
		'''Puts the name of the current page on the clipboard.'''
		Clipboard().set_pagelink(self.notebook, self.page)

	def show_preferences(self):
		from zim.gui.preferencesdialog import PreferencesDialog
		PreferencesDialog(self).run()

	def save_preferences(self):
		if self.preferences.modified:
			self.preferences.write_async()
			self.emit('preferences-changed')

	def do_preferences_changed(self):
		self.uimanager.set_add_tearoffs(
			self.preferences['GtkInterface']['tearoff_menus'] )

	def reload_page(self):
		if self.page.modified \
		and not self.save_page(self.page):
			raise AssertionError, 'Could not save page'
			# assert statement could be optimized away
		self.notebook.flush_page_cache(self.page)
		self.open_page(self.notebook.get_page(self.page))

	def attach_file(self, path=None):
		AttachFileDialog(self, path=path).run()

	def open_file(self, file):
		'''Open either a File or a Dir in the file browser'''
		assert isinstance(file, (File, Dir))
		if isinstance(file, (File)) and file.isdir():
			file = Dir(file.path)

		if file.exists():
			# TODO if isinstance(File) check default application for mime type
			# this is needed once we can set default app from "open with.." menu
			self._openwith(
				self.preferences['GtkInterface']['file_browser'], (file,) )
		else:
			ErrorDialog(self, NoSuchFileError(file)).run()

	def open_url(self, url):
		assert isinstance(url, basestring)
		if url.startswith('file:/'):
			self.open_file(File(url))
		elif url.startswith('mailto:'):
			self._openwith(self.preferences['GtkInterface']['email_client'], (url,))
		else:
			if is_win32_share_re.match(url):
				url = normalize_win32_share(url)
			self._openwith(self.preferences['GtkInterface']['web_browser'], (url,))

	def _openwith(self, name, args):
		entry = get_application(name)
		entry.spawn(args)

	def open_attachments_folder(self):
		dir = self.notebook.get_attachments_dir(self.page)
		if dir is None:
			error = _('This page does not have an attachments folder')
				# T: Error message
			ErrorDialog(self, error).run()
		elif dir.exists():
			self.open_file(dir)
		else:
			question = (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The attachments folder for this page does not yet exist.\nDo you want to create it now?'))
					# T: Text in a question dialog for creating a folder
			create = QuestionDialog(self, question).run()
			if create:
				dir.touch()
				self.open_file(dir)

	def open_notebook_folder(self):
		if self.notebook.dir:
			self.open_file(self.notebook.dir)
		elif self.notebook.file:
			self.open_file(self.notebook.file.dir)
		else:
			assert False, 'BUG: notebook has neither dir or file'

	def open_document_root(self):
		dir = self.notebook.get_document_root()
		if dir and dir.exists():
			self.open_file(dir)

	def open_document_folder(self):
		dir = self.notebook.get_document_root()
		if dir is None:
			return

		dirpath = encode_filename(self.page.name)
		dir = Dir([dir, dirpath])

		if dir.exists():
			self.open_file(dir)
		else:
			question = (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The document folder for this page does not yet exist.\nDo you want to create it now?'))
					# T: Text in a question dialog for creating a folder
			create = QuestionDialog(self, question).run()
			if create:
				dir.touch()
				self.open_file(dir)

	def edit_page_source(self):
		# This could also be defined as a custom tool, but defined here
		# because we want to determine the editor dynamically
		# We assume that the default app for a text file is a editor
		# and not e.g. a viewer or a browser. Of course users can still
		# define a custom tool for other editors.
		if hasattr(self.page, 'source'):
			file = self.page.source # TODO copy to tmp file
		else:
			ErrorDialog('This page does not have a source file').run()
			return

		application = get_application(
			self.preferences['GtkInterface']['file_browser'] )
		try:
			application.run((file,))
		except:
			logger.exception('Error while running %s:', application.name)
		else:
			# TODO copy back tmp file
			self.reload_page()

	def show_server_gui(self):
		# TODO instead of spawn, include in this process
		self.spawn('--server', '--gui', self.notebook.uri)

	def reload_index(self, flush=False):
		'''Show a progress bar while updating the notebook index.
		Returns True unless the user cancelled the action.
		'''
		# First make the index stop updating
		self.mainwindow.pageindex.disconnect_model()

		# Update the model
		index = self.notebook.index
		if flush:
			index.flush()

		dialog = ProgressBarDialog(self, _('Updating index'))
			# T: Title of progressbar dialog
		dialog.show_all()
		index.update(callback=lambda p: dialog.pulse(p.name))
		dialog.destroy()

		# And reconnect the model - flushing out any sync error in treemodel
		self.mainwindow.pageindex.reload_model()

		return not dialog.cancelled

	def manage_custom_tools(self):
		from zim.gui.customtools import CustomToolManagerDialog
		CustomToolManagerDialog(self).run()
		self.load_custom_tools()

	def load_custom_tools(self):
		manager = CustomToolManager()

		# Remove old actions
		if self._custom_tool_ui_id:
			self.uimanager.remove_ui(self._custom_tool_ui_id)

		if self._custom_tool_actiongroup:
			self.uimanager.remove_action_group(self._custom_tool_actiongroup)

		# Load new actions
		actions = []
		for tool in manager:
			# FIXME probably need to generate stock icon first if icon is file path
			action = (tool.key, tool.icon, tool.name, '', tool.comment, self.exec_custom_tool)
			actions.append(action)
		self._custom_tool_actiongroup = gtk.ActionGroup('custom_tools')
		self._custom_tool_actiongroup.add_actions(actions)

		menulines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager]
		toollines = ["<toolitem action='%s'/>\n" % tool.key for tool in manager if tool.showintoolbar]
		textlines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager if tool.showincontextmenu == 'Text']
		pagelines = ["<menuitem action='%s'/>\n" % tool.key for tool in manager if tool.showincontextmenu == 'Page']
		ui = """\
<ui>
	<menubar name='menubar'>
		<menu action='tools_menu'>
			<placeholder name='custom_tools'>
			 %s
			</placeholder>
		</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</toolbar>
	<popup name='text_popup'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</popup>
	<popup name='page_popup'>
		<placeholder name='tools'>
		%s
		</placeholder>
	</popup>
</ui>
""" % (
	''.join(menulines), ''.join(toollines),
	''.join(textlines), ''.join(pagelines)
)

		self.uimanager.insert_action_group(self._custom_tool_actiongroup, 0)
		self._custom_tool_ui_id = self.uimanager.add_ui_from_string(ui)

		# TODO also support toolbar, need to add icons to icon factory etc.

	def exec_custom_tool(self, action):
		manager = CustomToolManager()
		tool = manager.get_tool(action.get_name())
		logger.info('Execute custom tool %s', tool.name)
		args = (self.notebook, self.page, self.mainwindow.pageview)
		try:
			if tool.isreadonly:
				tool.spawn(args)
			else:
				tool.run(args)
				self.reload_page()
				#~ self.notebook.index.update(background=True)
				# TODO instead of using run, use spawn and show dialog
				# with cancel button. Dialog blocks ui.
		except Exception, error:
			ErrorDialog(self, error).run()

	def show_help(self, page=None):
		if page:
			self.spawn('--manual', page)
		else:
			self.spawn('--manual')

	def show_help_faq(self):
		self.show_help('FAQ')

	def show_help_keys(self):
		self.show_help('Help:Key Bindings')

	def show_help_bugs(self):
		self.show_help('Bugs')

	def show_about(self):
		gtk.about_dialog_set_url_hook(lambda d, l: self.open_url(l))
		gtk.about_dialog_set_email_hook(lambda d, l: self.open_url(l))
		dialog = gtk.AboutDialog()
		try: # since gtk 2.12
			dialog.set_program_name('Zim')
		except AttributeError:
			pass
		dialog.set_version(zim.__version__)
		dialog.set_comments(_('A desktop wiki'))
			# T: General description of zim itself
		dialog.set_copyright(zim.__copyright__)
		dialog.set_license(zim.__license__)
		dialog.set_authors([zim.__author__])
		dialog.set_translator_credits(_('translator-credits'))
			# T: This string needs to be translated with names of the translators for this language
		dialog.set_website(zim.__url__)
		dialog.run()
		dialog.destroy()

# Need to register classes defining gobject signals
gobject.type_register(GtkInterface)


class MainWindow(gtk.Window):
	'''Main window of the application, showing the page index in the side
	pane and a pageview with the current page. Alse includes the menubar,
	toolbar, statusbar etc.
	'''

	def __init__(self, ui, fullscreen=False, geometry=None):
		'''Constructor'''
		gtk.Window.__init__(self)
		self._fullscreen = False
		self.ui = ui

		ui.connect_after('open-notebook', self.do_open_notebook)
		ui.connect('open-page', self.do_open_page)
		ui.connect('close-page', self.do_close_page)
		ui.connect('preferences-changed', self.do_preferences_changed)

		self._sidepane_autoclose = False
		self._switch_focus_accelgroup = None

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		def do_delete_event(*a):
			logger.debug('Action: close (delete-event)')
			self.hide() # look more responsive
			ui.close()
			return True # Do not destroy - let close() handle it
		self.connect('delete-event', do_delete_event)

		vbox = gtk.VBox()
		self.add(vbox)

		# setup menubar and toolbar
		self.add_accel_group(ui.uimanager.get_accel_group())
		self.menubar = ui.uimanager.get_widget('/menubar')
		self.toolbar = ui.uimanager.get_widget('/toolbar')
		self.toolbar.connect('popup-context-menu', self.do_toolbar_popup)
		vbox.pack_start(self.menubar, False)
		vbox.pack_start(self.toolbar, False)

		# split window in side pane and editor
		self.hpane = gtk.HPaned()
		self.hpane.set_position(175)
		vbox.add(self.hpane)
		self.sidepane = gtk.VBox(spacing=5)
		self.hpane.add1(self.sidepane)

		self.sidepane.connect('key-press-event',
			lambda o, event: event.keyval == KEYVAL_ESC
				and self.toggle_sidepane())


		self.pageindex = PageIndex(ui)
		self.sidepane.add(self.pageindex)

		vbox2 = gtk.VBox()
		self.hpane.add2(vbox2)

		self.pathbar = None
		self.pathbar_box = gtk.HBox() # FIXME other class for this ?
		self.pathbar_box.set_border_width(3)
		vbox2.pack_start(self.pathbar_box, False)

		self.pageview = PageView(ui)
		self.pageview.view.connect_after(
			'toggle-overwrite', self.do_textview_toggle_overwrite)
		vbox2.add(self.pageview)

		# create statusbar
		hbox = gtk.HBox(spacing=0)
		vbox.pack_start(hbox, False, True, False)

		self.statusbar = gtk.Statusbar()
		#~ self.statusbar.set_has_resize_grip(False)
		self.statusbar.push(0, '<page>')
		hbox.add(self.statusbar)

		def statusbar_element(string, size):
			frame = gtk.Frame()
			frame.set_shadow_type(gtk.SHADOW_IN)
			self.statusbar.pack_end(frame, False)
			label = gtk.Label(string)
			label.set_size_request(size, 10)
			label.set_alignment(0.1, 0.5)
			frame.add(label)
			return label

		# specify statusbar elements right-to-left
		self.statusbar_style_label = statusbar_element('<style>', 100)
		self.statusbar_insert_label = statusbar_element('INS', 60)

		# and build the widget for backlinks
		self.statusbar_backlinks_button = \
			BackLinksMenuButton(self.ui, status_bar_style=True)
		frame = gtk.Frame()
		frame.set_shadow_type(gtk.SHADOW_IN)
		self.statusbar.pack_end(frame, False)
		frame.add(self.statusbar_backlinks_button)

		# add a second statusbar widget - somehow the corner grip
		# does not render properly after the pack_end for the first one
		#~ statusbar2 = gtk.Statusbar()
		#~ statusbar2.set_size_request(25, 10)
		#~ hbox.pack_end(statusbar2, False)

		self.do_preferences_changed()

		self._geometry_set = False
		self._set_fullscreen = False
		if geometry:
			try:
				self.parse_geometry(geometry)
				self._geometry_set = True
			except:
				logger.exception('Parsing geometry string failed:')
		elif fullscreen:
			self._set_fullscreen = True

	def do_update_statusbar(self, *a):
		page = self.pageview.get_page()
		if not page:
			return
		label = page.name
		if page.modified:
			label += '*'
		if self.ui.readonly or page.readonly:
			label += ' ['+_('readonly')+']' # T: page status in statusbar
		self.statusbar.pop(0)
		self.statusbar.push(0, label)

	def do_window_state_event(self, event):
		#~ print 'window-state changed:', event.changed_mask
		#~ print 'window-state new state:', event.new_window_state
		isfullscreen = gtk.gdk.WINDOW_STATE_FULLSCREEN
		if bool(event.changed_mask & isfullscreen):
			# Did not find property for this - so tracking state ourself
			self._fullscreen = bool(event.new_window_state & isfullscreen)
			logger.debug('Fullscreen changed: %s', self._fullscreen)
			self._set_widgets_visable()
			if self.actiongroup:
				# only do this after we initalize
				self.toggle_fullscreen(show=self._fullscreen)

	def do_preferences_changed(self, *a):
		if self._switch_focus_accelgroup:
			self.remove_accel_group(self._switch_focus_accelgroup)

		space = gtk.gdk.unicode_to_keyval(ord(' '))
		group = gtk.AccelGroup()
		group.connect_group( # <Alt><Space>
			space, gtk.gdk.MOD1_MASK, gtk.ACCEL_VISIBLE,
			self.do_switch_focus)
		if self.ui.preferences['GtkInterface']['toggle_on_ctrlspace']:
			group.connect_group( # <Ctrl><Space>
				space, gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE,
				self.do_switch_focus)

		self.add_accel_group(group)
		self._switch_focus_accelgroup = group

	def get_selected_path(self):
		'''Returns a selected path either from the side pane or the pathbar
		if any or None.
		'''
		# FIXME - this method is bound to break again - to unstable
		widget = self.get_focus()
		#~ print '>>>', widget
		if widget == self.pageindex.treeview:
			logger.debug('Pageindex has focus')
			return self.pageindex.get_selected_path()
		elif widget == self.pathbar:
			logger.debug('Pathbar has focus')
			return self.pathbar.get_selected_path()
		elif widget == self.pageview.view:
			logger.debug('Pageview has focus')
			return self.ui.page
		else:
			logger.debug('No path in focus mainwindow')
			return None

	def toggle_menubar(self, show=None):
		self.do_toggle_menubar(show=show)

	def do_toggle_menubar(self, show=None):
		if show:
			self.menubar.set_no_show_all(False)
			self.menubar.show()
		else:
			self.menubar.hide()
			self.menubar.set_no_show_all(True)

		if self._fullscreen:
			self.uistate['show_menubar_fullscreen'] = show
		else:
			self.uistate['show_menubar'] = show

	def toggle_toolbar(self, show=None):
		action = self.actiongroup.get_action('toggle_toolbar')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_toolbar(show=show)

	def do_toggle_toolbar(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_toolbar')
			show = action.get_active()

		if show:
			self.toolbar.set_no_show_all(False)
			self.toolbar.show()
		else:
			self.toolbar.hide()
			self.toolbar.set_no_show_all(True)

		if self._fullscreen:
			self.uistate['show_toolbar_fullscreen'] = show
		else:
			self.uistate['show_toolbar'] = show

	def do_toolbar_popup(self, toolbar, x, y, button):
		'''Show the context menu for the toolbar'''
		menu = self.ui.uimanager.get_widget('/toolbar_popup')
		menu.popup(None, None, None, button, 0)

	def toggle_statusbar(self, show=None):
		action = self.actiongroup.get_action('toggle_statusbar')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_statusbar(show=show)

	def do_toggle_statusbar(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_statusbar')
			show = action.get_active()

		if show:
			self.statusbar.set_no_show_all(False)
			self.statusbar.show()
		else:
			self.statusbar.hide()
			self.statusbar.set_no_show_all(True)

		if self._fullscreen:
			self.uistate['show_statusbar_fullscreen'] = show
		else:
			self.uistate['show_statusbar'] = show

	def toggle_fullscreen(self, show=None):
		action = self.actiongroup.get_action('toggle_fullscreen')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_fullscreen(show=show)

	def do_toggle_fullscreen(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_fullscreen')
			show = action.get_active()

		if show:
			self.fullscreen()
		else:
			self.unfullscreen()

	def toggle_sidepane(self, show=None):
		action = self.actiongroup.get_action('toggle_sidepane')
		if show is None or show != action.get_active():
			action.activate()
		else:
			self.do_toggle_sidepane(show=show)

	def do_toggle_sidepane(self, show=None):
		if show is None:
			action = self.actiongroup.get_action('toggle_sidepane')
			show = action.get_active()

		if show:
			self.sidepane.set_no_show_all(False)
			self.sidepane.show_all()
			self.hpane.set_position(self.uistate['sidepane_pos'])
			self.pageindex.grab_focus()
		else:
			self.uistate['sidepane_pos'] = self.hpane.get_position()
			self.sidepane.hide_all()
			self.sidepane.set_no_show_all(True)
			self.pageview.grab_focus()

		self._sidepane_autoclose = False
		self.uistate['show_sidepane'] = show

	def do_switch_focus(self, *a):
		action = self.actiongroup.get_action('toggle_sidepane')
		if action.get_active():
			# side pane open
			if self.pageindex.is_focus():
				# and has focus
				self.pageview.grab_focus()
				if self._sidepane_autoclose:
					self.toggle_sidepane(show=False)
			else:
				# but no focus
				self.pageindex.grab_focus()
		else:
			self.toggle_sidepane(show=True)
			self._sidepane_autoclose = True
			self.pageindex.grab_focus()

		return True # we are called from an event handler

	def set_pathbar(self, style):
		'''Set the pathbar. Style can be either PATHBAR_NONE,
		PATHBAR_RECENT, PATHBAR_HISTORY or PATHBAR_PATH.
		'''
		assert style in ('none', 'recent', 'history', 'path')
		self.actiongroup.get_action('set_pathbar_'+style).activate()

	def do_set_pathbar(self, action):
		name = action.get_name()
		style = name[12:] # len('set_pathbar_') == 12

		if style == PATHBAR_NONE:
			self.pathbar_box.hide()
			klass = None
		elif style == PATHBAR_HISTORY:
			klass = HistoryPathBar
		elif style == PATHBAR_RECENT:
			klass = RecentPathBar
		elif style == PATHBAR_PATH:
			klass = NamespacePathBar
		else:
			assert False, 'BUG: Unknown pathbar type %s' % style

		if not style == PATHBAR_NONE:
			if not (self.pathbar and self.pathbar.__class__ == klass):
				for child in self.pathbar_box.get_children():
					self.pathbar_box.remove(child)
				self.pathbar = klass(self.ui, spacing=3)
				self.pathbar.set_history(self.ui.history)
				self.pathbar_box.add(self.pathbar)
			self.pathbar_box.show_all()

		if self._fullscreen:
			self.uistate['pathbar_type_fullscreen'] = style
		else:
			self.uistate['pathbar_type'] = style

	def set_toolbar_style(self, style):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_AND_TEXT, TOOLBAR_ICONS_ONLY or TOOLBAR_TEXT_ONLY.
		'''
		assert style in ('icons_and_text', 'icons_only', 'text_only'), style
		self.actiongroup.get_action('set_toolbar_'+style).activate()

	def do_set_toolbar_style(self, action):
		name = action.get_name()
		style = name[12:] # len('set_toolbar_') == 12

		if style == TOOLBAR_ICONS_AND_TEXT:
			self.toolbar.set_style(gtk.TOOLBAR_BOTH)
		elif style == TOOLBAR_ICONS_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_ICONS)
		elif style == TOOLBAR_TEXT_ONLY:
			self.toolbar.set_style(gtk.TOOLBAR_TEXT)
		else:
			assert False, 'BUG: Unkown toolbar style: %s' % style

		self.uistate['toolbar_style'] = style

	def set_toolbar_size(self, size):
		'''Set the toolbar style. Style can be either
		TOOLBAR_ICONS_LARGE, TOOLBAR_ICONS_SMALL or TOOLBAR_ICONS_TINY.
		'''
		assert size in ('large', 'small', 'tiny'), size
		self.actiongroup.get_action('set_toolbar_icons_'+size).activate()

	def do_set_toolbar_size(self, action):
		name = action.get_name()
		size = name[18:] # len('set_toolbar_icons_') == 18

		if size == TOOLBAR_ICONS_LARGE:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_LARGE_TOOLBAR)
		elif size == TOOLBAR_ICONS_SMALL:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_SMALL_TOOLBAR)
		elif size == TOOLBAR_ICONS_TINY:
			self.toolbar.set_icon_size(gtk.ICON_SIZE_MENU)
		else:
			assert False, 'BUG: Unkown toolbar size: %s' % size

		self.uistate['toolbar_size'] = size

	def toggle_readonly(self, readonly=None):
		action = self.actiongroup.get_action('toggle_readonly')
		if readonly is None or readonly == action.get_active():
			action.activate()
		else:
			active = not readonly
			self.do_toggle_readonly(active=active)

	def do_toggle_readonly(self, active=None):
		if active is None:
			action = self.actiongroup.get_action('toggle_readonly')
			active = action.get_active()
		readonly = not active
		self.ui.set_readonly(readonly)
		self.uistate['readonly'] = readonly

	def do_open_notebook(self, ui, notebook):
		# Initialize all the uistate parameters
		# delayed till here because all this needs real uistate to be in place
		# also pathbar needs history in place
		self.uistate = ui.uistate['MainWindow']

		if not self._geometry_set:
			# Ignore this is a explicit geometry was specified to the constructor
			self.uistate.setdefault('windowsize', (600, 450), check=self.uistate.is_coord)
			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)

		self.uistate.setdefault('show_sidepane', True)
		self.uistate.setdefault('sidepane_pos', 200)
		self.uistate.setdefault('show_menubar', True)
		self.uistate.setdefault('show_menubar_fullscreen', True)
		self.uistate.setdefault('show_toolbar', True)
		self.uistate.setdefault('show_toolbar_fullscreen', False)
		self.uistate.setdefault('show_statusbar', True)
		self.uistate.setdefault('show_statusbar_fullscreen', False)
		self.uistate.setdefault('pathbar_type', PATHBAR_RECENT)
		self.uistate.setdefault('pathbar_type_fullscreen', PATHBAR_NONE)

		self._set_widgets_visable()
		self.toggle_sidepane(show=self.uistate['show_sidepane'])

		if 'toolbar_style' in self.uistate:
			self.set_toolbar_style(self.uistate['toolbar_style'])
		# else trust system default

		if 'toolbar_size' in self.uistate:
			self.set_toolbar_size(self.uistate['toolbar_size'])
		# else trust system default

		self.toggle_fullscreen(show=self._set_fullscreen)

		self.uistate.setdefault('readonly', False)
		if notebook.readonly:
			self.toggle_readonly(readonly=True)
			action = self.actiongroup.get_action('toggle_readonly')
			action.set_sensitive(False)
		else:
			self.toggle_readonly(readonly=self.uistate['readonly'])

		# And hook to notebook properties
		self.on_notebook_properties_changed(notebook)
		notebook.connect('properties-changed', self.on_notebook_properties_changed)

		# Hook up the statusbar
		self.ui.connect_after('open-page', self.do_update_statusbar)
		self.ui.connect_after('readonly-changed', self.do_update_statusbar)
		self.pageview.connect('modified-changed', self.do_update_statusbar)
		notebook.connect_after('stored-page', self.do_update_statusbar)

	def _set_widgets_visable(self):
		# Convenience method to switch visibility of all widgets
		if self._fullscreen:
			self.toggle_menubar(show=self.uistate['show_menubar_fullscreen'])
			self.toggle_toolbar(show=self.uistate['show_toolbar_fullscreen'])
			self.toggle_statusbar(show=self.uistate['show_statusbar_fullscreen'])
			self.set_pathbar(self.uistate['pathbar_type_fullscreen'])
		else:
			self.toggle_menubar(show=self.uistate['show_menubar'])
			self.toggle_toolbar(show=self.uistate['show_toolbar'])
			self.toggle_statusbar(show=self.uistate['show_statusbar'])
			self.set_pathbar(self.uistate['pathbar_type'])

	def on_notebook_properties_changed(self, notebook):
		self.set_title(notebook.name + ' - Zim')
		if notebook.icon:
			try:
				self.set_icon_from_file(notebook.icon)
			except gobject.GError:
				logger.exception('Could not load icon %s', notebook.icon)

	def do_open_page(self, ui, page, record):
		'''Signal handler for open-page, updates the pageview'''
		self.pageview.set_page(page)

		n = ui.notebook.index.n_list_links(page, zim.index.LINK_DIR_BACKWARD)
		label = self.statusbar_backlinks_button.label
		label.set_text_with_mnemonic(
			ngettext('%i _Backlink...', '%i _Backlinks...', n) % n)
			# T: Label for button with backlinks in statusbar
		if n == 0:
			self.statusbar_backlinks_button.set_sensitive(False)
		else:
			self.statusbar_backlinks_button.set_sensitive(True)

		#TODO: set toggle_readonly insensitive when page is readonly

	def do_close_page(self, ui, page):
		w, h = self.get_size()
		if not self._fullscreen:
			self.uistate['windowsize'] = (w, h)
		self.uistate['sidepane_pos'] = self.hpane.get_position()

	def do_textview_toggle_overwrite(self, view):
		state = view.get_overwrite()
		if state: text = 'OVR'
		else: text = 'INS'
		self.statusbar_insert_label.set_text(text)

# Need to register classes defining gobject signals or overloading methods
gobject.type_register(MainWindow)


class BackLinksMenuButton(MenuButton):

	def __init__(self, ui, status_bar_style=False):
		label = '%i _Backlinks...' % 0 # Translated above
		MenuButton.__init__(self, label, gtk.Menu(), status_bar_style)
		self.ui = ui

	def popup_menu(self, event=None):
		# Create menu on the fly
		self.menu = gtk.Menu()
		index = self.ui.notebook.index
		links = list(index.list_links(self.ui.page, LINK_DIR_BACKWARD))
		if not links:
			return

		self.menu.add(gtk.TearoffMenuItem())
			# TODO: hook tearoff to trigger search dialog

		for link in links:
			item = gtk.MenuItem(link.source.name)
			item.connect_object('activate', self.ui.open_page, link.source)
			self.menu.add(item)

		MenuButton.popup_menu(self, event)


class PageWindow(gtk.Window):
	'''Secondairy window, showing a single page'''

	def __init__(self, ui, page):
		gtk.Window.__init__(self)
		self.ui = ui

		self.set_title(page.name + ' - Zim')
		if ui.notebook.icon:
			try:
				self.set_icon_from_file(ui.notebook.icon)
			except gobject.GError:
				logger.exception('Could not load icon %s', ui.notebook.icon)


		page = ui.notebook.get_page(page)

		self.uistate = ui.uistate['PageWindow']
			# TODO remember for separate windows separately
			# e.g. use PageWindow1, PageWindow2, etc
		self.uistate.setdefault('windowsize', (500, 400), check=self.uistate.is_coord)
		w, h = self.uistate['windowsize']
		self.set_default_size(w, h)

		self.pageview = PageView(ui, secondairy=True)
		self.pageview.set_page(page)
		self.add(self.pageview)


def get_window(ui):
	'''Returns a gtk.Window object or None. Used to find the parent window
	for dialogs.
	'''
	if isinstance(ui, gtk.Window):
		return ui
	elif hasattr(ui, 'mainwindow'):
		return ui.mainwindow
	else:
		return None


class SavePageErrorDialog(ErrorDialog):
	'''Error dialog used when we hit an error while trying to save a page.
	Allow to save a copy or to discard changes. Includes a timer which
	delays the action buttons becoming sensitive. Reason for this timer is
	that the dialog may popup from auto-save while the user is typing, and
	we want to prevent an accidental action.
	'''

	def __init__(self, ui, error, page):
		title = _('Could not save page: %s') % page.name
			# T: Heading of error dialog
		explanation = _('''\
To continue you can save a copy of this page or discard
any changes. If you save a copy changes will be also
discarded, but you can restore the copy later.''')
			# T: text in error dialog when saving page failed
		gtk.MessageDialog.__init__(
			self, parent=get_window(ui),
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_NONE,
			message_format=title
		)
		#~ self.set_default_size(450, -1)
		self.format_secondary_text(
			unicode(error).encode('utf-8').strip()+'\n\n'+explanation)

		self.page = page
		self.error = error
		self.ui = ui

		self.timer_label = gtk.Label()
		self.timer_label.set_alignment(0.9, 0.5)
		self.timer_label.set_sensitive(False)
		self.timer_label.show()
		self.vbox.add(self.timer_label)

		cancel_button = gtk.Button(stock=gtk.STOCK_CANCEL)
		self.add_action_widget(cancel_button, gtk.RESPONSE_CANCEL)

		self._done = False
		def discard(self):
			self.ui.mainwindow.pageview.clear()
				# issue may be caused in pageview - make sure it unlocks
			self.ui.notebook.revert_page(self.page)
			self._done = True

		def save(self):
			if SaveCopyDialog(self, page=self.page).run():
				discard(self)

		discard_button = gtk.Button(_('_Discard Changes'))
			# T: Button in error dialog
		discard_button.connect_object('clicked', discard, self)
		self.add_action_widget(discard_button, gtk.RESPONSE_OK)

		save_button = Button(label=_('_Save Copy'), stock=gtk.STOCK_SAVE_AS)
			# T: Button in error dialog
		save_button.connect_object('clicked', save, self)
		self.add_action_widget(save_button, gtk.RESPONSE_OK)

		for button in (cancel_button, discard_button, save_button):
			button.set_sensitive(False)
			button.show()

	def do_response_ok(self):
		return self._done

	def run(self):
		self.timer = 5
		self.timer_label.set_text('%i sec.' % self.timer)
		def timer(self):
			self.timer -= 1
			if self.timer > 0:
				self.timer_label.set_text('%i sec.' % self.timer)
				return True # keep timer going
			else:
				for button in self.action_area.get_children():
					button.set_sensitive(True)
				self.timer_label.set_text('')
				return False # remove timer

		# older gobject version doesn't know about seconds
		id = gobject.timeout_add(1000, timer, self)
		ErrorDialog.run(self)
		gobject.source_remove(id)


class OpenPageDialog(Dialog):
	'''Dialog to go to a specific page. Also known as the "Jump to" dialog.
	Prompts for a page name and navigate to that page on 'Ok'.
	'''

	def __init__(self, ui, namespace=None):
		Dialog.__init__(self, ui, _('Jump to'), # T: Dialog title
			button=(None, gtk.STOCK_JUMP_TO),
			path_context = ui.page,
			fields=[('name', 'page', _('Jump to Page'), None)] # T: Label for page input
		)

	def do_response_ok(self):
		path = self.get_field('name')
		if path:
			self.ui.open_page(path)
			return True
		else:
			return False


class NewPageDialog(Dialog):
	'''Dialog used to create a new page, functionally it is almost the same
	as the OpenPageDialog except that the page is saved directly in order
	to create it.
	'''

	def __init__(self, ui, path=None, subpage=False):
		if subpage: title = _('New Sub Page') # T: Dialog title
		else: title = _('New Page') # T: Dialog title

		Dialog.__init__(self, ui, title,
			help_text=_(
				'Please note that linking to a non-existing page\n'
				'also creates a new page automatically.'),
			# T: Dialog text in 'new page' dialog
			path_context=path,
			fields=[('name', 'page', _('Page Name'), None)], # T: Input label
			help=':Help:Pages'
		)

		if subpage:
			print 'SETTING force_child'
			pageentry = self.inputs['name']
			pageentry.force_child = True

	def do_response_ok(self):
		path = self.get_field('name')
		if path:
			page = self.ui.notebook.get_page(path)
			if page.hascontent or page.haschildren:
				ErrorDialog(self, _('Page exists')+': %s' % page.name).run() # T: error message
				return False

			template = self.ui.notebook.get_template(page)
			tree = template.process_to_parsetree(self.ui.notebook, page)
			page.set_parsetree(tree)
			self.ui.save_page()

			self.ui.open_page(page)
			return True
		else:
			return False


class SaveCopyDialog(FileDialog):

	def __init__(self, ui, page=None):
		FileDialog.__init__(self, ui, _('Save Copy'), gtk.FILE_CHOOSER_ACTION_SAVE)
			# T: Dialog title of file save dialog
		self.filechooser.set_current_name(self.ui.page.name + '.txt')
		if page is None:
			page = self.ui.page
		self.page = page
		# TODO also include headers
		# TODO add droplist with native formats to choose + hook filters

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		format = 'wiki'
		logger.info("Saving a copy of %s using format '%s'", self.page, format)
		lines = self.page.dump(format)
		file.writelines(lines)
		self.result = True
		return True


class ImportPageDialog(FileDialog):
	# TODO how to properly detect file types for other formats ?

	def __init__(self, ui):
		FileDialog.__init__(self, ui, _('Import Page')) # T: Dialog title
		self.add_filter(_('Text Files'), '*.txt') # T: File filter for '*.txt'
		# TODO add input for namespace, format

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False

		basename = file.basename
		if basename.endswith('.txt'):
			basename = basename[:-4]

		path = self.ui.notebook.resolve_path(basename)
		page = self.ui.notebook.get_page(path)
		if page.hascontent:
			path = self.ui.notebook.index.get_unique_path(path)
			page = self.ui.notebook.get_page(path)
			assert not page.hascontent

		page.parse('wiki', file.readlines())
		self.ui.notebook.store_page(page)
		self.ui.open_page(page)
		return True


class MovePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Move Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		if isinstance(self.path, Page) \
		and self.path.modified \
		and not self.ui.save_page(self.path):
			raise AssertionError, 'Could not save page'
			# assert statement could be optimized away

		i = self.ui.notebook.index.n_list_links_to_tree(
					self.path, zim.index.LINK_DIR_BACKWARD )

		self.vbox.add(gtk.Label(_('Move page "%s"') % self.path.name))
			# T: Heading in 'move page' dialog - %s is the page name
		linkslabel = ngettext(
			'Update %i page linking to this page',
			'Update %i pages linking to this page', i) % i
			# T: label in MovePage dialog - %i is number of backlinks
			# TODO update lable to reflect that links can also be to child pages
		self.context_page = self.path.parent
		self.add_fields([
			('parent', 'namespace', _('Namespace'), self.context_page),
				# T: Input label for namespace to move a file to
			('links', 'bool', linkslabel, True),
				# T: option in 'move page' dialog
		])

		if i == 0:
			self.inputs['links'].set_active(False)
			self.inputs['links'].set_sensitive(False)

	def do_response_ok(self):
		parent = self.get_field('parent')
		links = self.get_field('links')
		newpath = parent + self.path.basename
		self.hide() # hide this dialog before showing the progressbar
		ok = self.ui.do_move_page(self.path, newpath, update_links=links)
		if ok:
			return True
		else:
			self.show() # prompt again
			return False


class RenamePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Rename Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		i = self.ui.notebook.index.n_list_links_to_tree(
					self.path, zim.index.LINK_DIR_BACKWARD )

		self.vbox.add(gtk.Label(_('Rename page "%s"') % self.path.name))
			# T: label in 'rename page' dialog - %s is the page name
		linkslabel = ngettext(
			'Update %i page linking to this page',
			'Update %i pages linking to this page', i) % i
			# T: label in MovePage dialog - %i is number of backlinks
			# TODO update lable to reflect that links can also be to child pages
		self.add_fields([
			('name', 'string', _('Name'), self.path.basename),
				# T: Input label in the 'rename page' dialog for the new name
			('head', 'bool', _('Update the heading of this page'), True),
				# T: Option in the 'rename page' dialog
			('links', 'bool', linkslabel, True),
				# T: Option in the 'rename page' dialog
		])

		if i == 0:
			self.inputs['links'].set_active(False)
			self.inputs['links'].set_sensitive(False)

	def do_response_ok(self):
		name = self.get_field('name')
		head = self.get_field('head')
		links = self.get_field('links')
		self.hide() # hide this dialog before showing the progressbar
		ok = self.ui.do_rename_page(
			self.path, newbasename=name, update_heading=head, update_links=links)
		if ok:
			return True
		else:
			self.show() # prompt again
			return False

class DeletePageDialog(Dialog):

	def __init__(self, ui, path=None):
		Dialog.__init__(self, ui, _('Delete Page')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)
		img = gtk.image_new_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
		hbox.add(img)
		label = gtk.Label()
		short = _('Delete page "%s"?') % self.path.basename
			# T: Heading in 'delete page' dialog - %s is the page name
		long = _('Page "%s" and all of it\'s sub-pages and attachments will be deleted') % self.path.name
			# T: Text in 'delete page' dialog - %s is the page name
		label.set_markup('<b>'+short+'</b>\n\n'+long)
		hbox.add(label)

	def do_response_ok(self):
		try:
			self.ui.notebook.delete_page(self.path)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False
		else:
			return True


class AttachFileDialog(FileDialog):

	def __init__(self, ui, path=None):
		FileDialog.__init__(self, ui, _('Attach File')) # T: Dialog title
		if path is None:
			self.path = self.ui.get_path_context()
		else:
			self.path = path
		assert self.path, 'Need a page here'

		self.dir = self.ui.notebook.get_attachments_dir(self.path)
		if self.dir is None:
			ErrorDialog(_('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception, 'Page "%s" does not have a folder for attachments' % self.path

		self.uistate.setdefault('insert_attached_images', True)
		checkbox = gtk.CheckButton(_('Insert images as link'))
			# T: checkbox in the "Attach File" dialog
		checkbox.set_active(self.uistate['insert_attached_images'])
		self.filechooser.set_extra_widget(checkbox)

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False

		checkbox = self.filechooser.get_extra_widget()
		self.uistate['insert_attached_images'] = checkbox.get_active()
			# Similar code in zim.gui.InsertImageDialog

		file.copyto(self.dir)
		file = self.dir.file(file.basename)
		pageview = self.ui.mainwindow.pageview
		if self.uistate['insert_attached_images'] and file.isimage():
			try:
				pageview.insert_image(file, interactive=False)
			except:
				logger.exception('Could not insert image')
				pageview.insert_links([file]) # image type not supported?
		else:
			pageview.insert_links([file])
		return True

