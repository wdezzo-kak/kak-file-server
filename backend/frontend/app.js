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
    this.sortBy = 'name';
    this.sortOrder = 'asc';
    
    // Move modal state
    this.moveCurrentPath = '/';
    this.folderCache = {};
    
    this.init();
  }
  
  init() {
    this.bindElements();
    this.bindEvents();
    // Set initial view mode to list
    this.viewMode = 'list';
    this.fileGrid.classList.add('list-view');
    if (this.listViewHeader) {
      this.listViewHeader.style.display = 'flex';
    }
    // Set list icon on view toggle button
    const viewToggleBtn = document.getElementById('viewToggle');
    if (viewToggleBtn) {
      viewToggleBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="4" cy="5" r="1.5"/>
          <circle cx="4" cy="12" r="1.5"/>
          <circle cx="4" cy="19" r="1.5"/>
          <rect x="8" y="4" width="14" height="2" rx="1"/>
          <rect x="8" y="11" width="14" height="2" rx="1"/>
          <rect x="8" y="18" width="14" height="2" rx="1"/>
        </svg>
        `;
    }
    
    // Initialize sidebar tree (only once)
    this.initSidebarTree();
    
    this.loadFiles();
  }
  
  async initSidebarTree() {
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (!sidebarNav) return;
    
    // Only load if not already loaded
    if (sidebarNav.dataset.loaded === 'true') return;
    
    sidebarNav.innerHTML = '<div class="sidebar-loading">Loading tree...</div>';
    
    try {
      const response = await fetch(`${API_BASE}?recursive`);
      const data = await response.json();
      
      const paths = data.results || [];
      
      // Build tree structure
      const pathMap = new Map();
      
      // First pass: create all nodes
      paths.forEach(item => {
        const path = item.path || '/';
        const name = path.split('/').filter(Boolean).pop() || '/';
        
        pathMap.set(path, {
          name: name,
          path: path,
          is_dir: item.is_dir,
          children: []
        });
      });
      
      // Second pass: build hierarchy
      const tree = [];
      pathMap.forEach((node, path) => {
        const parentPath = path.substring(0, path.length - node.name.length - 1) || '/';
        
        if (parentPath === '' || parentPath === '/') {
          tree.push(node);
        } else {
          const parent = pathMap.get(parentPath);
          if (parent && parent.is_dir) {
            parent.children.push(node);
          }
        }
      });
      
      // Store tree for quick access
      this.directoryTree = tree;
      this.pathMap = pathMap;
      
      // Render tree
      const html = this.renderTreeNodes(tree, '');
      sidebarNav.innerHTML = html;
      sidebarNav.dataset.loaded = 'true';
      
      // Add click handlers
      sidebarNav.querySelectorAll('.tree-folder-row').forEach(row => {
        row.addEventListener('click', (e) => {
          // Don't toggle if clicking the open button
          if (e.target.classList.contains('tree-open-btn')) return;
          const item = row.closest('.tree-folder-item');
          item.classList.toggle('expanded');
        });
      });
      
      // Open button click - navigate to folder
      sidebarNav.querySelectorAll('.tree-open-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const path = btn.dataset.path;
          this.navigateTo(path);
        });
      });
      
      sidebarNav.querySelectorAll('.tree-file').forEach(link => {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          const path = link.dataset.path;
          this.openFile(path);
        });
      });
      
      // Drag and drop for files
      this.initSidebarDragDrop();
      
    } catch (error) {
      console.error('Failed to load directory tree:', error);
      sidebarNav.innerHTML = '<div class="sidebar-empty">Failed to load</div>';
    }
    
    // Calculate and update storage info
    this.updateStorageInfo();
  }
  
  async updateStorageInfo() {
    const storageText = document.querySelector('.storage-text');
    const storageUsed = document.querySelector('.storage-used');
    const storageBar = document.querySelector('.storage-bar');
    
    if (!storageText) return;
    
    try {
      // Fetch file stats
      const response = await fetch(`${API_BASE}?stats`);
      const data = await response.json();
      
      const totalSpace = data.total_space || 0;
      const freeSpace = data.free_space || 0;
      const usedSpace = data.used_space || 0;
      const fileCount = data.file_count || 0;
      const folderCount = data.folder_count || 0;
      
      // Format size
      const formatSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
      };
      
      const usedPercent = totalSpace > 0 ? Math.round((usedSpace / totalSpace) * 100) : 0;
      
      if (storageUsed) {
        storageUsed.style.width = `${usedPercent}%`;
      }
      
      storageText.innerHTML = `
        <div>${formatSize(usedSpace)} used of ${formatSize(totalSpace)}</div>
        <div style="font-size: 11px; color: var(--text-muted);">${formatSize(freeSpace)} free • ${fileCount} files • ${folderCount} folders</div>
      `;
      
    } catch (error) {
      console.error('Failed to get storage info:', error);
      storageText.textContent = 'Unable to load';
    }
  }
  
  expandSidebarFolder(path) {
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (!sidebarNav) return;
    
    // Normalize path - ensure it ends with /
    let normalizedPath = path;
    if (!normalizedPath.endsWith('/')) {
      normalizedPath += '/';
    }
    
    // Find the folder item and expand it
    const folderItem = sidebarNav.querySelector(`.tree-folder-item[data-path="${normalizedPath}"]`);
    if (folderItem) {
      folderItem.classList.add('expanded');
      
      // Also expand parent folders
      const parts = normalizedPath.split('/').filter(Boolean);
      if (parts.length > 1) {
        const parentPath = '/' + parts.slice(0, -1).join('/') + '/';
        if (parentPath && parentPath !== '//') {
          this.expandSidebarFolder(parentPath);
        }
      }
    }
  }
  
  initSidebarDragDrop() {
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (!sidebarNav) return;
    
    let draggedItem = null;
    
    // Make files draggable
    sidebarNav.querySelectorAll('.tree-file-item').forEach(item => {
      item.setAttribute('draggable', 'true');
      
      item.addEventListener('dragstart', (e) => {
        draggedItem = item;
        item.classList.add('dragging');
        e.dataTransfer.setData('text/plain', item.dataset.path);
        e.dataTransfer.effectAllowed = 'move';
      });
      
      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        draggedItem = null;
      });
    });
    
    // Make folders drop targets
    sidebarNav.querySelectorAll('.tree-folder-item').forEach(item => {
      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        item.classList.add('drag-over');
      });
      
      item.addEventListener('dragleave', () => {
        item.classList.remove('drag-over');
      });
      
      item.addEventListener('drop', async (e) => {
        e.preventDefault();
        item.classList.remove('drag-over');
        
        const srcPath = e.dataTransfer.getData('text/plain');
        const destPath = item.dataset.path;
        
        if (srcPath && destPath && srcPath !== destPath) {
          // Move the file
          this.selectedFiles.clear();
          this.selectedFiles.add(srcPath);
          this.moveCurrentPath = destPath;
          
          await this.moveSelectedFiles();
        }
      });
    });
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
    this.listViewHeader = document.getElementById('listViewHeader');
    this.sortDropdown = document.getElementById('sortDropdown');
    this.moveFolderTree = document.getElementById('moveFolderTree');
    this.movePathDisplay = document.getElementById('movePathDisplay');
  }
  
  bindEvents() {
    // Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const mobileMenuOverlay = document.getElementById('mobileMenuOverlay');
    const closeMobileMenu = document.getElementById('closeMobileMenu');
    
    if (mobileMenuBtn) {
      mobileMenuBtn.addEventListener('click', () => {
        mobileMenuOverlay.classList.add('open');
      });
    }
    
    if (closeMobileMenu) {
      closeMobileMenu.addEventListener('click', () => {
        mobileMenuOverlay.classList.remove('open');
      });
    }
    
    // Sidebar buttons
    const sidebarNewFolderBtn = document.getElementById('sidebarNewFolderBtn');
    if (sidebarNewFolderBtn) {
      sidebarNewFolderBtn.addEventListener('click', () => {
        this.openNewFolderModal();
      });
    }
    
    const sidebarUploadBtn = document.getElementById('sidebarUploadBtn');
    if (sidebarUploadBtn) {
      sidebarUploadBtn.addEventListener('click', () => {
        this.openUploadModal();
      });
    }
    
    const sidebarDownloadZipBtn = document.getElementById('sidebarDownloadZipBtn');
    if (sidebarDownloadZipBtn) {
      sidebarDownloadZipBtn.addEventListener('click', () => {
        this.downloadZip();
      });
    }
    
    // Navigation
    document.getElementById('backBtn').addEventListener('click', () => this.goBack());
    document.getElementById('forwardBtn').addEventListener('click', () => this.goForward());
    document.getElementById('refreshBtn').addEventListener('click', () => this.loadFiles());
    
    // View toggle
    document.getElementById('viewToggle').addEventListener('click', () => this.toggleView());
    
    // Dark mode toggle
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
      darkModeToggle.addEventListener('click', () => this.toggleDarkMode());
    }
    
    // Check for saved dark mode preference
    this.initDarkMode();
    
    // Mobile search toggle
    const mobileSearchToggle = document.getElementById('mobileSearchToggle');
    const searchBox = document.querySelector('.search-box');
    const searchInput = document.getElementById('searchInput');
    const headerCenter = document.querySelector('.header-center');
    
    if (mobileSearchToggle && searchBox) {
      mobileSearchToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        searchBox.classList.toggle('expanded');
        
        // Also show header-center when search is expanded in mobile
        if (searchBox.classList.contains('expanded') && headerCenter) {
          headerCenter.style.display = 'block';
          headerCenter.style.position = 'fixed';
          headerCenter.style.top = '10px';
          headerCenter.style.left = '60px';
          headerCenter.style.right = '60px';
          headerCenter.style.zIndex = '999';
        }
        
        if (searchBox.classList.contains('expanded')) {
          searchInput.focus();
        }
      });
      
      // Close search when clicking outside
      searchInput.addEventListener('blur', () => {
        if (!searchInput.value) {
          searchBox.classList.remove('expanded');
          if (headerCenter && window.innerWidth <= 768) {
            headerCenter.style.display = '';
            headerCenter.style.position = '';
            headerCenter.style.top = '';
            headerCenter.style.left = '';
            headerCenter.style.right = '';
            headerCenter.style.zIndex = '';
          }
        }
      });
    }
    
    // Mobile search overlay
    const mobileSearchOverlay = document.getElementById('mobileSearchOverlay');
    const mobileSearchInput = document.getElementById('mobileSearchInput');
    const closeMobileSearch = document.getElementById('closeMobileSearch');
    const clearMobileSearch = document.getElementById('clearMobileSearch');
    
    if (mobileSearchToggle && mobileSearchOverlay) {
      mobileSearchToggle.addEventListener('click', () => {
        mobileSearchOverlay.classList.add('open');
        mobileSearchInput.focus();
      });
    }
    
    if (closeMobileSearch) {
      closeMobileSearch.addEventListener('click', () => {
        mobileSearchOverlay.classList.remove('open');
        mobileSearchInput.value = '';
        this.loadFiles();
      });
    }
    
    if (clearMobileSearch) {
      clearMobileSearch.addEventListener('click', () => {
        mobileSearchInput.value = '';
        mobileSearchInput.focus();
        this.loadFiles();
      });
    }
    
    if (mobileSearchInput) {
      let mobileSearchTimeout;
      mobileSearchInput.addEventListener('input', (e) => {
        clearTimeout(mobileSearchTimeout);
        mobileSearchTimeout = setTimeout(() => {
          this.handleMobileSearch(e.target.value);
        }, 300);
      });
    }
    
    // FAB button - opens upload modal
    const fabUpload = document.getElementById('fabUpload');
    if (fabUpload) {
      fabUpload.addEventListener('click', () => {
        this.openUploadModal();
      });
    }
    
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
    document.getElementById('sortBtn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleSortDropdown();
    });
    
    // Sort dropdown options
    document.querySelectorAll('.sort-option').forEach(option => {
      option.addEventListener('click', (e) => {
        const sortBy = e.currentTarget.dataset.sort;
        this.setSort(sortBy);
      });
    });
    
    // Close sort dropdown when clicking outside
    document.addEventListener('click', () => {
      if (this.sortDropdown.classList.contains('open')) {
        this.sortDropdown.classList.remove('open');
      }
    });
    
    // List view header sort columns
    document.querySelectorAll('.list-col[data-sort]').forEach(col => {
      col.addEventListener('click', () => {
        const sortBy = col.dataset.sort;
        this.setSort(sortBy);
      });
    });
  }
  
  async loadFiles() {
    // Don't show loading state if we have cached files
    const hasCache = this.files.length > 0;
    if (!hasCache) {
      this.showLoading();
    }
    
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
      this.updateSidebarActive();
      
      // Only update sidebar tree if navigating to a different path
      // (don't re-fetch tree on every navigation for performance)
    } catch (error) {
      console.error('Failed to load files:', error);
      this.showEmpty();
    }
  }
  
  updateSidebarActive() {
    const sidebarNav = document.querySelector('.sidebar-nav');
    if (!sidebarNav) return;
    
    // First expand the current path in the sidebar
    this.expandSidebarFolder(this.currentPath);
    
    // Update active state on tree items
    sidebarNav.querySelectorAll('.tree-folder').forEach(btn => {
      const path = btn.dataset.path;
      if (path === this.currentPath) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }
  
  renderTreeNodes(nodes, basePath) {
    if (!nodes || nodes.length === 0) return '';
    
    let html = '';
    
    // Sort: folders first, then files
    const sortedNodes = [...nodes].sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;
      return a.name.localeCompare(b.name);
    });
    
    sortedNodes.forEach(node => {
      if (node.is_dir) {
        const hasChildren = node.children && node.children.length > 0;
        const isActive = node.path === this.currentPath;
        
        html += `
          <div class="tree-item tree-folder-item" data-path="${node.path}/">
            <div class="tree-folder-row ${isActive ? 'active' : ''}">
              <button class="nav-item tree-folder" data-path="${node.path}/">
                ${hasChildren ? '<svg class="tree-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>' : '<span class="tree-spacer"></span>'}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <span class="tree-name">${node.name}</span>
              </button>
              <button class="tree-open-btn" data-path="${node.path}/" title="Open">Open</button>
            </div>
            ${hasChildren ? `<div class="tree-children">${this.renderTreeNodes(node.children, node.path)}</div>` : ''}
          </div>
        `;
      } else {
        // Render file with proper icon
        const fileIcon = this.getFileIcon(node.name);
        
        html += `
          <div class="tree-item tree-file-item" draggable="true" data-path="${node.path}">
            <a href="#" class="nav-item tree-file" data-path="${node.path}">
              <span class="file-icon">${fileIcon}</span>
              <span class="tree-name">${node.name}</span>
            </a>
          </div>
        `;
      }
    });
    
    return html;
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
    
    // Ensure list-view class is applied based on viewMode
    this.fileGrid.classList.toggle('list-view', this.viewMode === 'list');
    
    // Show/hide list view header based on view mode
    if (this.listViewHeader) {
      this.listViewHeader.style.display = this.viewMode === 'list' ? 'flex' : 'none';
    }
    
    // Sort: directories first, then by selected field
    const sorted = [...this.files].sort((a, b) => {
      // Directories always first
      if (a.is_dir && !b.is_dir) return -1;
      if (!a.is_dir && b.is_dir) return 1;
      
      let cmp = 0;
      switch (this.sortBy) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;
        case 'size':
          cmp = (a.size || 0) - (b.size || 0);
          break;
        case 'modified':
          cmp = (a.mtime || 0) - (b.mtime || 0);
          break;
        default:
          cmp = a.name.localeCompare(b.name);
      }
      
      return this.sortOrder === 'desc' ? -cmp : cmp;
    });
    
    this.updateSortIcons();
    
    this.fileGrid.innerHTML = sorted.map(file => this.renderFileItem(file)).join('');
    
    // Bind file events
    this.fileGrid.querySelectorAll('.file-item').forEach(item => {
      const path = item.dataset.path;
      const isDir = item.dataset.isDir === 'true';
      
      let pressTimer;
      let isSelecting = false;
      
      // Mouse down - start press timer
      item.addEventListener('mousedown', (e) => {
        if (e.target.closest('.file-checkbox') || e.target.closest('.file-checkbox-wrapper')) return;
        if (e.target.closest('.file-options-btn')) return;
        
        pressTimer = setTimeout(() => {
          // Long press - select the item (and keep it selected)
          if (!this.selectedFiles.has(path)) {
            this.toggleSelect(path);
          }
          isSelecting = true;
        }, 300); // 300ms hold to select
      });
      
      // Mouse up - cancel timer
      item.addEventListener('mouseup', (e) => {
        clearTimeout(pressTimer);
        isSelecting = false;
      });
      
      // Mouse leave - cancel timer
      item.addEventListener('mouseleave', () => {
        clearTimeout(pressTimer);
        isSelecting = false;
      });
      
      // Click on file item - toggle select if any file is selected, otherwise open
      item.addEventListener('click', (e) => {
        if (e.target.closest('.file-checkbox') || e.target.closest('.file-checkbox-wrapper')) return;
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
    
    // Drag selection
    let isDragging = false;
    let dragStartItem = null;
    
    this.fileGrid.addEventListener('mousedown', (e) => {
      if (e.target.closest('.file-item') && !e.target.closest('.file-checkbox') && 
          !e.target.closest('.file-checkbox-wrapper') && !e.target.closest('.file-options-btn')) {
        isDragging = true;
        dragStartItem = e.target.closest('.file-item');
      }
    });
    
    this.fileGrid.addEventListener('mousemove', (e) => {
      if (!isDragging || !dragStartItem) return;
      
      const targetItem = e.target.closest('.file-item');
      if (targetItem) {
        const targetPath = targetItem.dataset.path;
        if (!this.selectedFiles.has(targetPath)) {
          this.toggleSelect(targetPath);
        }
      }
    });
    
    document.addEventListener('mouseup', () => {
      isDragging = false;
      dragStartItem = null;
    });
  }
  
  renderFileItem(file) {
    const isSelected = this.selectedFiles.has(file.path);
    const icon = file.is_dir ? this.getFolderIcon() : this.getFileIcon(file.name);
    const size = file.is_dir ? '-' : this.formatSize(file.size);
    const modified = file.mtime ? this.formatDate(file.mtime * 1000) : '-';
    
    return `
      <div class="file-item ${isSelected ? 'selected' : ''}" data-path="${file.path}" data-is-dir="${file.is_dir}">
        <div class="file-checkbox-wrapper">
          <input type="checkbox" class="file-checkbox" ${isSelected ? 'checked' : ''}>
          <span class="file-checkbox-custom"></span>
        </div>
        <div class="file-icon ${file.is_dir ? 'folder' : ''}">
          ${icon}
        </div>
        <div class="file-name" title="${file.name}">
          <div class="file-name-text">${file.name}</div>
        </div>
        <div class="file-size">${size}</div>
        <div class="file-modified">${modified}</div>
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
    
    // Image files
    const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico', 'tiff', 'psd', 'raw', 'heic'];
    // Document files
    const docExts = ['doc', 'docx', 'pdf', 'txt', 'md', 'rtf', 'odt', 'ppt', 'pptx', 'xls', 'xlsx', 'csv'];
    // Code files
    const codeExts = ['js', 'ts', 'jsx', 'tsx', 'py', 'html', 'htm', 'css', 'scss', 'sass', 'less', 'json', 'xml', 'yaml', 'yml', 'toml', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'go', 'rs', 'rb', 'php', 'swift', 'kt', 'sql', 'sh', 'bash', 'zsh', 'ps1'];
    // Video files
    const videoExts = ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpeg', 'mpg'];
    // Audio files
    const audioExts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus'];
    // Archive files
    const archiveExts = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'iso', 'dmg'];
    // Font files
    const fontExts = ['ttf', 'otf', 'woff', 'woff2', 'eot'];
    
    // Default file icon
    let iconColor = 'currentColor';
    let icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>`;
    
    if (imageExts.includes(ext)) {
      iconColor = '#10b981';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <circle cx="8.5" cy="8.5" r="1.5"/>
        <polyline points="21 15 16 10 5 21"/>
      </svg>`;
    } else if (docExts.includes(ext)) {
      if (ext === 'pdf') {
        iconColor = '#ef4444';
        icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <path d="M10 12h4M10 16h4"/>
        </svg>`;
      } else if (['md', 'txt', 'rtf'].includes(ext)) {
        iconColor = '#6b7280';
        icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>`;
      } else {
        iconColor = '#3b82f6';
        icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>`;
      }
    } else if (codeExts.includes(ext)) {
      iconColor = '#f59e0b';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <polyline points="16 18 22 12 16 6"/>
        <polyline points="8 6 2 12 8 18"/>
      </svg>`;
    } else if (videoExts.includes(ext)) {
      iconColor = '#8b5cf6';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/>
        <line x1="7" y1="2" x2="7" y2="22"/>
        <line x1="17" y1="2" x2="17" y2="22"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <line x1="2" y1="7" x2="7" y2="7"/>
        <line x1="2" y1="17" x2="7" y2="17"/>
        <line x1="17" y1="17" x2="22" y2="17"/>
        <line x1="17" y1="7" x2="22" y2="7"/>
      </svg>`;
    } else if (audioExts.includes(ext)) {
      iconColor = '#ec4899';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <path d="M9 18V5l12-2v13"/>
        <circle cx="6" cy="18" r="3"/>
        <circle cx="18" cy="16" r="3"/>
      </svg>`;
    } else if (archiveExts.includes(ext)) {
      iconColor = '#f97316';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <path d="M21 8v13H3V8"/>
        <path d="M1 3h22v5H1z"/>
        <path d="M10 12h4"/>
      </svg>`;
    } else if (fontExts.includes(ext)) {
      iconColor = '#14b8a6';
      icon = `<svg viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="1.5">
        <polyline points="4 7 4 4 20 20 20 20 20 7"/>
        <path d="M9 20V7h5"/>
        <path d="M15 4v16"/>
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
    
    // Update UI - both class and checkbox state
    document.querySelectorAll('.file-item').forEach(item => {
      const itemPath = item.dataset.path;
      const checkbox = item.querySelector('.file-checkbox');
      
      if (this.selectedFiles.has(itemPath)) {
        item.classList.add('selected');
        if (checkbox) checkbox.checked = true;
      } else {
        item.classList.remove('selected');
        if (checkbox) checkbox.checked = false;
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
    if (this.listViewHeader) {
      this.listViewHeader.style.display = this.viewMode === 'list' ? 'flex' : 'none';
    }
    
    // Update view toggle icon
    const viewToggleBtn = document.getElementById('viewToggle');
    if (this.viewMode === 'list') {
      // List view icon - 3 dots with 3 lines
      viewToggleBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="4" cy="5" r="1.5"/>
          <circle cx="4" cy="12" r="1.5"/>
          <circle cx="4" cy="19" r="1.5"/>
          <rect x="8" y="4" width="14" height="2" rx="1"/>
          <rect x="8" y="11" width="14" height="2" rx="1"/>
          <rect x="8" y="18" width="14" height="2" rx="1"/>
        </svg>
      `;
    } else {
      // Grid view icon - 4 squares
      viewToggleBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7"/>
          <rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/>
          <rect x="3" y="14" width="7" height="7"/>
        </svg>
      `;
    }
    
    this.renderFiles();
  }
  
  // Dark Mode
  initDarkMode() {
    // Check localStorage first
    const savedTheme = localStorage.getItem('kak-theme');
    if (savedTheme === 'dark') {
      document.body.classList.add('dark-mode');
    } else if (savedTheme === 'light') {
      document.body.classList.remove('dark-mode');
    } else {
      // Check system preference
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.body.classList.add('dark-mode');
      }
    }
  }
  
  toggleDarkMode() {
    const isDark = document.body.classList.toggle('dark-mode');
    localStorage.setItem('kak-theme', isDark ? 'dark' : 'light');
  }
  
  toggleSort() {
    this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    this.renderFiles();
    this.updateSortIcons();
  }
  
  toggleSortDropdown() {
    const sortBtn = document.getElementById('sortBtn');
    const sortDropdown = this.sortDropdown;
    
    if (sortBtn && sortDropdown) {
      const rect = sortBtn.getBoundingClientRect();
      
      // Position dropdown below the sort button
      sortDropdown.style.position = 'fixed';
      sortDropdown.style.top = `${rect.bottom + 4}px`;
      sortDropdown.style.right = `${window.innerWidth - rect.right}px`;
      sortDropdown.style.left = 'auto';
    }
    
    sortDropdown.classList.toggle('open');
  }
  
  setSort(sortBy) {
    // If clicking the same sort, toggle order
    if (this.sortBy === sortBy) {
      this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortBy = sortBy;
      this.sortOrder = 'asc';
    }
    this.sortDropdown.classList.remove('open');
    this.renderFiles();
    this.updateSortIcons();
  }
  
  updateSortIcons() {
    // Update header sort icons
    document.querySelectorAll('.list-col[data-sort]').forEach(col => {
      const sortBy = col.dataset.sort;
      const icon = col.querySelector('.sort-icon');
      if (sortBy === this.sortBy) {
        icon.innerHTML = this.sortOrder === 'asc' 
          ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m18 15-6-6-6 6"/></svg>'
          : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>';
      } else {
        icon.innerHTML = '';
      }
    });
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
      <button class="options-menu-item" data-action="move">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 9l-3 3 3 3"/>
          <path d="M9 5l3-3 3 3"/>
          <path d="M15 19l-3 3-3-3"/>
          <path d="M19 9l3 3-3 3"/>
          <line x1="2" y1="12" x2="22" y2="12"/>
          <line x1="12" y1="2" x2="12" y2="22"/>
        </svg>
        <span>Move</span>
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
          case 'move':
            this.selectedFiles.clear();
            this.selectedFiles.add(path);
            this.updateSelectionUI();
            this.openMoveModal();
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
      case 'copylink':
        this.copyLink(path);
        break;
      case 'share':
        await this.shareFile(path);
        break;
      case 'rename':
        this.showRenameDialog(path);
        break;
      case 'delete':
        await this.deleteFile(path);
        break;
    }
  }
  
  copyLink(path) {
    const link = `${window.location.origin}${path}`;
    navigator.clipboard.writeText(link).then(() => {
      this.showNotification('Link copied to clipboard!');
    }).catch(() => {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = link;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      this.showNotification('Link copied to clipboard!');
    });
  }
  
  async shareFile(path) {
    try {
      const response = await fetch(`${API_BASE}/__dufs__/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path, expires_in: 86400 })
      });
      
      if (response.ok) {
        const data = await response.json();
        const shareLink = data.url;
        
        // Copy share link
        navigator.clipboard.writeText(shareLink).then(() => {
          this.showNotification('Share link copied to clipboard!');
        }).catch(() => {
          // Fallback - show in prompt
          prompt('Share link:', shareLink);
        });
      } else {
        this.showNotification('Failed to create share link');
      }
    } catch (error) {
      console.error('Share failed:', error);
      this.showNotification('Failed to create share link');
    }
  }
  
  showNotification(message) {
    // Simple notification - could be enhanced
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      background: var(--primary);
      color: white;
      padding: 12px 24px;
      border-radius: var(--radius);
      box-shadow: var(--shadow-lg);
      z-index: 10000;
      animation: slideIn 0.3s ease;
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.remove();
    }, 3000);
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
    
    // Show upload progress container
    const progressContainer = document.getElementById('uploadProgressContainer');
    if (progressContainer) {
      progressContainer.style.display = 'block';
    }
    
    // Calculate total size
    let totalSize = 0;
    for (const file of files) {
      totalSize += file.size;
    }
    
    let uploadedSize = 0;
    const startTime = Date.now();
    
    for (const file of files) {
      await this.uploadFile(file, (uploaded) => {
        // Update overall progress
        const currentTotal = uploadedSize + uploaded;
        const percent = Math.round((currentTotal / totalSize) * 100);
        
        // Update progress bar
        const progressFill = document.getElementById('uploadProgressFill');
        if (progressFill) {
          progressFill.style.width = percent + '%';
        }
        
        // Update bytes text
        const bytesText = document.getElementById('uploadBytes');
        if (bytesText) {
          bytesText.textContent = `${this.formatSize(currentTotal)} / ${this.formatSize(totalSize)}`;
        }
        
        // Update percent text
        const percentText = document.getElementById('uploadPercent');
        if (percentText) {
          percentText.textContent = percent + '%';
        }
        
        // Calculate and display speed
        const elapsed = (Date.now() - startTime) / 1000; // seconds
        if (elapsed > 0) {
          const speed = currentTotal / elapsed;
          const speedText = document.getElementById('uploadSpeed');
          if (speedText) {
            speedText.textContent = this.formatSize(speed) + '/s';
          }
        }
      });
      uploadedSize += file.size;
    }
    
    // Hide progress container
    if (progressContainer) {
      progressContainer.style.display = 'none';
    }
    
    setTimeout(() => {
      this.closeUploadModal();
      this.loadFiles();
    }, 1000);
  }
  
  async uploadFile(file, onProgress) {
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
      // Use XMLHttpRequest for progress tracking
      const response = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const percent = (e.loaded / e.total) * 100;
            progressBar.style.width = percent + '%';
            if (onProgress) {
              onProgress(e.loaded);
            }
          }
        });
        
        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(xhr);
          } else {
            reject(new Error('Upload failed'));
          }
        });
        
        xhr.addEventListener('error', () => reject(new Error('Upload failed')));
        
        xhr.open('PUT', `${API_BASE}${this.currentPath}${file.name}`);
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        xhr.send(file);
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
    this.moveCurrentPath = this.currentPath;
    this.folderCache = {};
    this.renderMoveFolderTree('/');
    this.updateMovePathDisplay();
  }
  
  closeMoveModal() {
    this.moveModal.classList.remove('open');
    this.folderCache = {};
  }
  
  updateMovePathDisplay() {
    this.movePathDisplay.textContent = this.moveCurrentPath;
  }
  
  async renderMoveFolderTree(path) {
    this.moveCurrentPath = path;
    this.updateMovePathDisplay();
    
    // Show loading
    this.moveFolderTree.innerHTML = '<div class="move-tree-loading">Loading...</div>';
    
    try {
      const response = await fetch(`${API_BASE}${path}?json`);
      const data = await response.json();
      
      const folders = (data.paths || []).filter(f => f.is_dir);
      
      // Cache the folders
      this.folderCache[path] = folders;
      
      this.renderFolderItems(folders, path);
    } catch (error) {
      console.error('Failed to load folders:', error);
      this.moveFolderTree.innerHTML = '<div class="move-tree-error">Failed to load folders</div>';
    }
  }
  
  renderFolderItems(folders, currentPath) {
    if (currentPath !== '/') {
      // Add parent directory option
      const parentPath = currentPath.endsWith('/') 
        ? currentPath.slice(0, -1).split('/').slice(0, -1).join('/') || '/'
        : currentPath.split('/').slice(0, -1).join('/') || '/';
      
      this.moveFolderTree.innerHTML = `
        <div class="move-folder-item" data-path="${parentPath}">
          <svg class="folder-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="m15 18-6-6 6-6"/>
          </svg>
          <span class="folder-name">.. (Parent)</span>
        </div>
      `;
    } else {
      this.moveFolderTree.innerHTML = '';
    }
    
    folders.forEach(folder => {
      const folderPath = folder.path;
      const item = document.createElement('div');
      item.className = 'move-folder-item';
      item.dataset.path = folderPath;
      item.innerHTML = `
        <svg class="folder-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span class="folder-name">${folder.name}</span>
        <svg class="chevron-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      `;
      
      item.addEventListener('click', () => {
        this.renderMoveFolderTree(folderPath + '/');
      });
      
      this.moveFolderTree.appendChild(item);
    });
    
    // Add click handler for parent
    const parentItem = this.moveFolderTree.querySelector('[data-path]:first-child');
    if (parentItem && parentItem.dataset.path !== currentPath) {
      parentItem.addEventListener('click', () => {
        this.renderMoveFolderTree(parentItem.dataset.path);
      });
    }
  }
  
  async moveSelectedFiles() {
    const destPath = this.moveCurrentPath;
    
    // Don't allow moving to the same directory
    if (destPath === this.currentPath) {
      alert('Cannot move files to the same location');
      return;
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
      
      // Update breadcrumb to show search
      this.breadcrumb.innerHTML = `<span class="breadcrumb-item">Search: "${query}"</span>`;
    } catch (error) {
      console.error('Search failed:', error);
    }
  }
  
  async handleMobileSearch(query) {
    const mobileSearchOverlay = document.getElementById('mobileSearchOverlay');
    const mobileSearchResults = document.getElementById('mobileSearchResults');
    
    if (!query) {
      mobileSearchResults.innerHTML = '';
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE}${this.currentPath}?q=${encodeURIComponent(query)}`);
      const data = await response.json();
      
      const results = data.results || [];
      
      if (results.length === 0) {
        mobileSearchResults.innerHTML = '<div class="mobile-search-empty">No files found</div>';
        return;
      }
      
      mobileSearchResults.innerHTML = results.map(file => {
        const icon = file.is_dir ? this.getFolderIcon() : this.getFileIcon(file.name);
        const size = file.is_dir ? '-' : this.formatSize(file.size);
        
        return `
          <div class="mobile-search-item" data-path="${file.path}" data-is-dir="${file.is_dir}">
            <div class="mobile-search-icon">${icon}</div>
            <div class="mobile-search-info">
              <div class="mobile-search-name">${file.name}</div>
              <div class="mobile-search-size">${size}</div>
            </div>
          </div>
        `;
      }).join('');
      
      // Add click handlers
      mobileSearchResults.querySelectorAll('.mobile-search-item').forEach(item => {
        item.addEventListener('click', () => {
          const path = item.dataset.path;
          const isDir = item.dataset.isDir === 'true';
          
          mobileSearchOverlay.classList.remove('open');
          
          if (isDir) {
            this.navigateTo(path + '/');
          } else {
            this.openFile(path);
          }
        });
      });
    } catch (error) {
      console.error('Mobile search failed:', error);
      mobileSearchResults.innerHTML = '<div class="mobile-search-empty">Search failed</div>';
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
    
    // Also update toolbar breadcrumb
    const toolbarBreadcrumb = document.getElementById('toolbarBreadcrumb');
    if (toolbarBreadcrumb) {
      toolbarBreadcrumb.innerHTML = html;
    }
    
    this.breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
      item.addEventListener('click', () => {
        this.navigateTo(item.dataset.path);
      });
    });
    
    if (toolbarBreadcrumb) {
      toolbarBreadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {
        item.addEventListener('click', () => {
          this.navigateTo(item.dataset.path);
        });
      });
    }
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
    this.hideLoading();
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
