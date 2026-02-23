// File Manager Application
const API_BASE = window.location.origin;

class FileManager {
  constructor() {
    this.currentPath = '/';
    this.files = [];
    this.selectedFiles = new Set();
    this.history = ['/'];
    this.historyIndex = 0;
    this.viewMode = 'list';
    this.sortOrder = 'asc';
    
    this.init();
  }
  
  init() {
    this.bindElements();
    this.bindEvents();
    this.loadFiles();
  }
  
  bindElements() {
    this.fileGrid = document.getElementById('fileGrid');
    this.loadingState = document.getElementById('loadingState');
    this.emptyState = document.getElementById('emptyState');
    this.breadcrumb = document.getElementById('breadcrumb');
    this.itemCount = document.getElementById('itemCount');
    this.selectAll = document.getElementById('selectAll');
    this.selectionActions = document.getElementById('selectionActions');
    this.selectionCount = document.getElementById('selectionCount');
    this.contextMenu = document.getElementById('contextMenu');
    this.uploadModal = document.getElementById('uploadModal');
    this.newFolderModal = document.getElementById('newFolderModal');
    this.moveModal = document.getElementById('moveModal');
    this.uploadDropzone = document.getElementById('uploadDropzone');
    this.fileInput = document.getElementById('fileInput');
    this.uploadList = document.getElementById('uploadList');
  }
  
  bindEvents() {
    // Navigation
    document.getElementById('backBtn').addEventListener('click', () => this.goBack());
    document.getElementById('forwardBtn').addEventListener('click', () => this.goForward());
    document.getElementById('refreshBtn').addEventListener('click', () => this.loadFiles());
    
    // View toggle
    document.getElementById('viewToggle').addEventListener('click', () => this.toggleView());
    
    // Upload
    document.getElementById('uploadBtn').addEventListener('click', () => this.openUploadModal());
    document.getElementById('closeUploadModal').addEventListener('click', () => this.closeUploadModal());
    document.getElementById('browseFiles').addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', (e) => this.handleFiles(e.target.files));
    
    // Drag & drop
    this.uploadDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.uploadDropzone.classList.add('dragover');
    });
    this.uploadDropzone.addEventListener('dragleave', () => {
      this.uploadDropzone.classList.remove('dragover');
    });
    this.uploadDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      this.uploadDropzone.classList.remove('dragover');
      this.handleFiles(e.dataTransfer.files);
    });
    
    // New folder
    document.getElementById('closeNewFolderModal').addEventListener('click', () => this.closeNewFolderModal());
    document.getElementById('cancelNewFolder').addEventListener('click', () => this.closeNewFolderModal());
    document.getElementById('createFolder').addEventListener('click', () => this.createFolder());
    
    // Selection
    this.selectAll.addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));
    
    // Delete selected
    document.getElementById('deleteSelected').addEventListener('click', () => this.deleteSelected());
    
    // Download selected
    document.getElementById('downloadSelected').addEventListener('click', () => this.downloadSelected());
    
    // Move selected
    document.getElementById('moveSelected').addEventListener('click', () => this.openMoveModal());
    
    // Download ZIP
    document.getElementById('downloadZipBtn').addEventListener('click', () => this.downloadZip());
    
    // New folder
    document.getElementById('newFolderBtn').addEventListener('click', () => this.openNewFolderModal());
    
    // Move modal events
    document.getElementById('closeMoveModal').addEventListener('click', () => this.closeMoveModal());
    document.getElementById('cancelMove').addEventListener('click', () => this.closeMoveModal());
    document.getElementById('confirmMove').addEventListener('click', () => this.moveSelectedFiles());
    
    // Context menu
    document.addEventListener('click', () => this.closeContextMenu());
    document.querySelectorAll('.context-item').forEach(item => {
      item.addEventListener('click', (e) => this.handleContextAction(e));
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    
    // Modal backdrop click
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
      backdrop.addEventListener('click', () => {
        document.querySelectorAll('.modal.open').forEach(modal => modal.classList.remove('open'));
      });
    });
    
    // Search
    document.getElementById('searchInput').addEventListener('input', (e) => this.handleSearch(e.target.value));
    
    // Sort
    document.getElementById('sortBtn').addEventListener('click', () => this.toggleSort());
  }
  
  async loadFiles() {
    this.showLoading();
    
    try {
      const response = await fetch(`${API_BASE}${this.currentPath}?json`);
      const data = await response.json();
      
      this.files = data.paths || [];
      this.permissions = {
        allow_upload: data.allow_upload,
        allow_delete: data.allow_delete,
        allow_search: data.allow_search,
        allow_archive: data.allow_archive
      };
      
      this.updatePermissionsUI();
      this.renderFiles();
      this.updateBreadcrumb();
      this.updateItemCount();
    } catch (error) {
      console.error('Failed to load files:', error);
      this.showEmpty();
    }
  }
  
  updatePermissionsUI() {
    // Show/hide buttons based on permissions
    const uploadBtn = document.getElementById('uploadBtn');
    const downloadZipBtn = document.getElementById('downloadZipBtn');
    const newFolderBtn = document.getElementById('newFolderBtn');
    
    if (uploadBtn) {
      uploadBtn.style.display = this.permissions?.allow_upload ? '' : 'none';
    }
    if (downloadZipBtn) {
      downloadZipBtn.style.display = this.permissions?.allow_archive ? '' : 'none';
    }
    if (newFolderBtn) {
      newFolderBtn.style.display = this.permissions?.allow_upload ? '' : 'none';
    }
  }
  
  renderFiles() {
    if (this.files.length === 0) {
      this.showEmpty();
      return;
    }
    
    this.hideLoading();
    this.hideEmpty();
    
    // Sort: directories first, then by name
    const sorted = [...this.files].sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;
      const cmp = a.name.localeCompare(b.name);
      return this.sortOrder === 'desc' ? -cmp : cmp;
    });
    
    this.fileGrid.innerHTML = sorted.map(file => this.renderFileItem(file)).join('');
    
    // Bind file events
    this.fileGrid.querySelectorAll('.file-item').forEach(item => {
      const path = item.dataset.path;
      const isDir = item.dataset.isDir === 'true';
      
      // Click on file item - toggle select if any file is selected, otherwise open
      item.addEventListener('click', (e) => {
        if (e.target.closest('.file-checkbox')) return;
        if (e.target.closest('.file-options-btn')) return;
        
        // If any file is selected, toggle this file's selection
        if (this.selectedFiles.size > 0) {
          this.toggleSelect(path);
        } else {
          // No files selected - open file/folder
          if (isDir) {
            this.navigateTo(path + '/');
          } else {
            this.openFile(path);
          }
        }
      });
      
      // Checkbox is for selection only
      const checkbox = item.querySelector('.file-checkbox');
      checkbox.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleSelect(path);
      });
      
      // Options button
      const optionsBtn = item.querySelector('.file-options-btn');
      optionsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.showOptionsMenu(e, path, isDir);
      });
    });
  }
  
  renderFileItem(file) {
    const isSelected = this.selectedFiles.has(file.path);
    const icon = file.is_dir ? this.getFolderIcon() : this.getFileIcon(file.name);
    const size = file.is_dir ? '-' : this.formatSize(file.size);
    const modified = this.formatDate(file.mtime * 1000);
    
    return `
      <div class="file-item ${isSelected ? 'selected' : ''}" data-path="${file.path}" data-is-dir="${file.is_dir}">
        <input type="checkbox" class="file-checkbox" ${isSelected ? 'checked' : ''}>
        <div class="file-icon ${file.is_dir ? 'folder' : ''}">
          ${icon}
        </div>
        <div class="file-name" title="${file.name}">
          <div class="file-name-text">${file.name}</div>
          <div class="file-size">${size}</div>
        </div>
        <button class="file-options-btn" data-path="${file.path}" data-is-dir="${file.is_dir}" title="Options">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="2"/>
            <circle cx="12" cy="12" r="2"/>
            <circle cx="12" cy="19" r="2"/>
          </svg>
        </button>
      </div>
    `;
  }
  
  getFolderIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    </svg>`;
  }
  
  getFileIcon(filename) {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp'];
    const docExts = ['doc', 'docx', 'pdf', 'txt', 'md', 'rtf'];
    const codeExts = ['js', 'ts', 'py', 'html', 'css', 'json', 'xml', 'java'];
    const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz'];
    
    let icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>`;
    
    if (imageExts.includes(ext)) {
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <circle cx="8.5" cy="8.5" r="1.5"/>
        <polyline points="21 15 16 10 5 21"/>
      </svg>`;
    } else if (docExts.includes(ext)) {
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
      </svg>`;
    } else if (codeExts.includes(ext)) {
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <polyline points="16 18 22 12 16 6"/>
        <polyline points="8 6 2 12 8 18"/>
      </svg>`;
    } else if (archiveExts.includes(ext)) {
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 8v13H3V8"/>
        <path d="M1 3h22v5H1z"/>
        <path d="M10 12h4"/>
      </svg>`;
    }
    
    return icon;
  }
  
  navigateTo(path) {
    this.currentPath = path;
    this.selectedFiles.clear();
    this.updateSelectionUI();
    
    // Add to history
    if (this.history[this.historyIndex] !== path) {
      this.history = this.history.slice(0, this.historyIndex + 1);
      this.history.push(path);
      this.historyIndex = this.history.length - 1;
    }
    
    this.loadFiles();
  }
  
  goBack() {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.currentPath = this.history[this.historyIndex];
      this.selectedFiles.clear();
      this.updateSelectionUI();
      this.loadFiles();
    }
  }
  
  goForward() {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.currentPath = this.history[this.historyIndex];
      this.selectedFiles.clear();
      this.updateSelectionUI();
      this.loadFiles();
    }
  }
  
  openFile(path) {
    window.open(`${API_BASE}${path}`, '_blank');
  }
  
  toggleSelect(path) {
    if (this.selectedFiles.has(path)) {
      this.selectedFiles.delete(path);
    } else {
      this.selectedFiles.add(path);
    }
    this.updateSelectionUI();
    
    // Update UI
    document.querySelectorAll('.file-item').forEach(item => {
      if (this.selectedFiles.has(item.dataset.path)) {
        item.classList.add('selected');
      } else {
        item.classList.remove('selected');
      }
    });
  }
  
  toggleSelectAll(checked) {
    if (checked) {
      this.files.forEach(file => this.selectedFiles.add(file.path));
    } else {
      this.selectedFiles.clear();
    }
    this.updateSelectionUI();
    this.renderFiles();
  }
  
  updateSelectionUI() {
    const count = this.selectedFiles.size;
    
    if (count > 0) {
      this.selectionActions.style.display = 'flex';
      this.selectionCount.textContent = `${count} selected`;
      this.selectAll.checked = count === this.files.length;
      this.selectAll.indeterminate = count > 0 && count < this.files.length;
    } else {
      this.selectionActions.style.display = 'none';
    }
  }
  
  toggleView() {
    this.viewMode = this.viewMode === 'grid' ? 'list' : 'grid';
    this.fileGrid.classList.toggle('list-view', this.viewMode === 'list');
  }
  
  toggleSort() {
    this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    this.renderFiles();
  }
  
  showContextMenu(e, path, isDir) {
    this.contextPath = path;
    this.contextIsDir = isDir;
    
    const x = Math.min(e.clientX, window.innerWidth - 200);
    const y = Math.min(e.clientY, window.innerHeight - 200);
    
    this.contextMenu.style.left = `${x}px`;
    this.contextMenu.style.top = `${y}px`;
    this.contextMenu.classList.add('open');
  }
  
  showOptionsMenu(e, path, isDir) {
    // Remove any existing options menu
    const existing = document.querySelector('.file-options-menu');
    if (existing) existing.remove();
    
    const filename = path.split('/').pop();
    const downloadText = isDir ? 'Download as ZIP' : 'Download';
    
    const menu = document.createElement('div');
    menu.className = 'file-options-menu';
    menu.innerHTML = `
      <button class="options-menu-item" data-action="download" data-is-dir="${isDir}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <span>${downloadText}</span>
      </button>
      <button class="options-menu-item" data-action="rename">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>
        </svg>
        <span>Rename</span>
      </button>
      <button class="options-menu-item danger" data-action="delete">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
        <span>Delete</span>
      </button>
    `;
    
    // Position the menu to the right of the button
    const btn = e.currentTarget;
    const rect = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.right = `${window.innerWidth - rect.right}px`;
    menu.style.top = `${rect.top}px`;
    menu.style.zIndex = '1000';
    
    document.body.appendChild(menu);
    
    // Add click handlers
    menu.querySelectorAll('.options-menu-item').forEach(item => {
      item.addEventListener('click', async (evt) => {
        const action = evt.currentTarget.dataset.action;
        const itemIsDir = evt.currentTarget.dataset.isDir === 'true';
        menu.remove();
        
        switch (action) {
          case 'download':
            if (itemIsDir) {
              // Folder - download as ZIP
              const folderPath = path.endsWith('/') ? path : path + '/';
              const zipUrl = `${API_BASE}${folderPath}?zip`;
              const link = document.createElement('a');
              link.href = zipUrl;
              link.download = filename + '.zip';
              link.click();
            } else {
              // File - download with attribute
              const link = document.createElement('a');
              link.href = `${API_BASE}${path}`;
              link.download = filename;
              link.target = '_blank';
              link.click();
            }
            break;
          case 'rename':
            this.showRenameDialog(path);
            break;
          case 'delete':
            await this.deleteFile(path);
            break;
        }
      });
    });
    
    // Close menu when clicking elsewhere
    const closeMenu = (evt) => {
      if (!menu.contains(evt.target)) {
        menu.remove();
        document.removeEventListener('click', closeMenu);
      }
    };
    setTimeout(() => document.addEventListener('click', closeMenu), 0);
  }
  
  closeContextMenu() {
    this.contextMenu.classList.remove('open');
  }
  
  async handleContextAction(e) {
    const action = e.currentTarget.dataset.action;
    const path = this.contextPath;
    
    this.closeContextMenu();
    
    switch (action) {
      case 'open':
        if (this.contextIsDir) {
          this.navigateTo(path + '/');
        } else {
          this.openFile(path);
        }
        break;
      case 'download':
        window.location.href = `${API_BASE}${path}`;
        break;
      case 'rename':
        this.showRenameDialog(path);
        break;
      case 'delete':
        await this.deleteFile(path);
        break;
    }
  }
  
  async deleteFile(path) {
    if (!confirm('Are you sure you want to delete this item?')) return;
    
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        this.loadFiles();
      } else {
        alert('Failed to delete file');
      }
    } catch (error) {
      console.error('Delete failed:', error);
      alert('Failed to delete file');
    }
  }
  
  async deleteSelected() {
    if (!confirm(`Delete ${this.selectedFiles.size} items?`)) return;
    
    for (const path of this.selectedFiles) {
      await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
    }
    
    this.selectedFiles.clear();
    this.updateSelectionUI();
    this.loadFiles();
  }
  
  showRenameDialog(path) {
    const name = prompt('Enter new name:', path.split('/').pop());
    if (!name || name === path.split('/').pop()) return;
    
    this.renameFile(path, name);
  }
  
  async renameFile(oldPath, newName) {
    const parent = oldPath.substring(0, oldPath.lastIndexOf('/') + 1);
    const newPath = parent + newName;
    
    try {
      const response = await fetch(`${API_BASE}${oldPath}`, {
        method: 'MOVE',
        headers: {
          'Destination': `${API_BASE}${newPath}`
        }
      });
      
      if (response.ok) {
        this.loadFiles();
      } else {
        alert('Failed to rename');
      }
    } catch (error) {
      console.error('Rename failed:', error);
      alert('Failed to rename');
    }
  }
  
  openUploadModal() {
    this.uploadModal.classList.add('open');
  }
  
  closeUploadModal() {
    this.uploadModal.classList.remove('open');
    this.uploadList.innerHTML = '';
    this.fileInput.value = '';
  }
  
  async handleFiles(files) {
    if (!files.length) return;
    
    this.uploadList.innerHTML = '';
    
    for (const file of files) {
      await this.uploadFile(file);
    }
    
    setTimeout(() => {
      this.closeUploadModal();
      this.loadFiles();
    }, 1000);
  }
  
  async uploadFile(file) {
    const item = document.createElement('div');
    item.className = 'upload-item';
    item.innerHTML = `
      <div class="upload-item-icon">
        ${this.getFileIcon(file.name)}
      </div>
      <div class="upload-item-info">
        <div class="upload-item-name">${file.name}</div>
        <div class="upload-item-size">${this.formatSize(file.size)}</div>
        <div class="upload-item-progress">
          <div class="upload-item-progress-bar" style="width: 0%"></div>
        </div>
      </div>
    `;
    this.uploadList.appendChild(item);
    
    const progressBar = item.querySelector('.upload-item-progress-bar');
    
    try {
      const response = await fetch(`${API_BASE}${this.currentPath}${file.name}`, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': 'application/octet-stream'
        }
      });
      
      if (response.ok) {
        progressBar.style.width = '100%';
      } else {
        progressBar.style.background = 'var(--error)';
        item.querySelector('.upload-item-name').textContent += ' (Failed)';
      }
    } catch (error) {
      console.error('Upload failed:', error);
      progressBar.style.background = 'var(--error)';
    }
  }
  
  openNewFolderModal() {
    this.newFolderModal.classList.add('open');
    document.getElementById('newFolderName').focus();
  }
  
  closeNewFolderModal() {
    this.newFolderModal.classList.remove('open');
    document.getElementById('newFolderName').value = '';
  }
  
  async createFolder() {
    const name = document.getElementById('newFolderName').value.trim();
    if (!name) return;
    
    try {
      const response = await fetch(`${API_BASE}${this.currentPath}${name}`, {
        method: 'MKCOL'
      });
      
      if (response.ok) {
        this.closeNewFolderModal();
        this.loadFiles();
      } else {
        alert('Failed to create folder');
      }
    } catch (error) {
      console.error('Create folder failed:', error);
    }
  }
  
  openMoveModal() {
    this.moveModal.classList.add('open');
    document.getElementById('moveDestination').value = this.currentPath;
    document.getElementById('moveDestination').focus();
  }
  
  closeMoveModal() {
    this.moveModal.classList.remove('open');
    document.getElementById('moveDestination').value = '';
  }
  
  async moveSelectedFiles() {
    const dest = document.getElementById('moveDestination').value.trim();
    if (!dest) return;
    
    let destPath = dest;
    if (!destPath.startsWith('/')) {
      destPath = this.currentPath + dest;
    }
    if (!destPath.endsWith('/')) {
      destPath += '/';
    }
    
    try {
      for (const srcPath of this.selectedFiles) {
        const filename = srcPath.split('/').pop();
        const newPath = destPath + filename;
        
        const response = await fetch(`${API_BASE}${srcPath}`, {
          method: 'MOVE',
          headers: {
            'Destination': `${API_BASE}${newPath}`
          }
        });
        
        if (!response.ok) {
          console.error(`Failed to move ${filename}`);
        }
      }
      
      this.selectedFiles.clear();
      this.updateSelectionUI();
      this.closeMoveModal();
      this.loadFiles();
    } catch (error) {
      console.error('Move failed:', error);
      alert('Failed to move files');
    }
  }
  
  async handleSearch(query) {
    if (!query) {
      this.loadFiles();
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE}${this.currentPath}?q=${encodeURIComponent(query)}`);
      const data = await response.json();
      
      this.files = data.results || [];
      this.renderFiles();
      this.updateItemCount();
    } catch (error) {
      console.error('Search failed:', error);
    }
  }
  
  updateBreadcrumb() {
    const parts = this.currentPath.split('/').filter(Boolean);
    let path = '';
    
    let html = '<span class="breadcrumb-item" data-path="/">Home</span>';
    
    for (const part of parts) {
      path += '/' + part;
      html += `<span class="breadcrumb-item" data-path="${path}">${part}</span>`;
    }
    
    this.breadcrumb.innerHTML = html;
    
    this.breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
      item.addEventListener('click', () => {
        this.navigateTo(item.dataset.path);
      });
    });
  }
  
  updateItemCount() {
    this.itemCount.textContent = `${this.files.length} items`;
  }
  
  showLoading() {
    this.loadingState.style.display = 'flex';
    this.fileGrid.style.display = 'none';
    this.emptyState.style.display = 'none';
  }
  
  hideLoading() {
    this.loadingState.style.display = 'none';
    this.fileGrid.style.display = '';
  }
  
  showEmpty() {
    this.fileGrid.innerHTML = '';
    this.fileGrid.style.display = 'none';
    this.emptyState.style.display = 'flex';
  }
  
  hideEmpty() {
    this.emptyState.style.display = 'none';
  }
  
  handleKeyboard(e) {
    // Cmd/Ctrl + K for search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      document.getElementById('searchInput').focus();
    }
    
    // Escape to close modals
    if (e.key === 'Escape') {
      this.closeContextMenu();
      this.closeUploadModal();
      this.closeNewFolderModal();
      this.closeMoveModal();
    }
  }
  
  downloadZip() {
    // Download current directory as ZIP
    let path = this.currentPath;
    if (!path.endsWith('/')) {
      path = path + '/';
    }
    const zipUrl = `${API_BASE}${path}?zip`;
    const link = document.createElement('a');
    link.href = zipUrl;
    link.download = this.currentPath.split('/').pop() || 'archive.zip';
    link.click();
  }
  
  downloadSelected() {
    // Download selected files
    if (this.selectedFiles.size === 0) return;
    
    if (this.selectedFiles.size === 1) {
      // Single file - download directly
      const path = Array.from(this.selectedFiles)[0];
      const filename = path.split('/').pop();
      const link = document.createElement('a');
      link.href = `${API_BASE}${path}`;
      link.download = filename;
      link.target = '_blank';
      link.click();
    } else {
      // Multiple files - download as zip of current folder
      this.downloadZip();
    }
  }
  
  formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }
  
  formatDate(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 86400000) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diff < 604800000) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
  window.fileManager = new FileManager();
});
