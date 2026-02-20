// API base URL - use relative path to work from any host
const API_URL = '/api';

// ─── Theme Management ────────────────────────────────────────────────────────
// Runs as an IIFE so the correct theme is applied before first paint,
// preventing a flash of the wrong colour scheme.
const Theme = (() => {
    const STORAGE_KEY = 'theme';
    const LIGHT = 'light';
    const html = document.documentElement;

    /** Resolve starting theme: saved preference → OS preference → dark */
    function getInitial() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: light)').matches ? LIGHT : 'dark';
    }

    /** Write the theme attribute (or remove it for dark, the default). */
    function apply(theme) {
        if (theme === LIGHT) {
            html.setAttribute('data-theme', LIGHT);
        } else {
            html.removeAttribute('data-theme');
        }
    }

    /** Return the currently active theme name. */
    function current() {
        return html.getAttribute('data-theme') === LIGHT ? LIGHT : 'dark';
    }

    /**
     * Flip to the opposite theme, persist the choice, and return the new value.
     * A brief `theme-transitioning` class is added to <html> for the duration of
     * the CSS transition so callers can react if needed.
     */
    function toggle() {
        const next = current() === LIGHT ? 'dark' : LIGHT;
        html.classList.add('theme-transitioning');
        apply(next);
        localStorage.setItem(STORAGE_KEY, next);
        // Remove the helper class after the longest transition completes (300 ms)
        setTimeout(() => html.classList.remove('theme-transitioning'), 350);
        return next;
    }

    // Apply the resolved theme immediately — before the DOM is ready.
    apply(getInitial());

    return { toggle, current };
})();

// Wire up the toggle button once the DOM is available.
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');

    function syncLabel() {
        themeToggle.setAttribute(
            'aria-label',
            Theme.current() === 'light' ? 'Switch to dark mode' : 'Switch to light mode'
        );
    }

    themeToggle.addEventListener('click', () => {
        Theme.toggle();
        syncLabel();
    });

    // Keep the label in sync with whatever theme was restored on load.
    syncLabel();
});

// Configure marked to open all links in a new tab
// marked v5+ passes a token object; older versions pass (href, title, text)
const markedRenderer = new marked.Renderer();
markedRenderer.link = function(token) {
    const href = typeof token === 'object' ? token.href : token;
    const title = typeof token === 'object' ? token.title : arguments[1];
    const text = typeof token === 'object' ? token.text : arguments[2];
    const titleAttr = title ? ` title="${title}"` : '';
    return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};
marked.setOptions({ renderer: markedRenderer });

// Global state
let currentSessionId = null;

// DOM elements
let chatMessages, chatInput, sendButton, totalCourses, courseTitles;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements after page loads
    chatMessages = document.getElementById('chatMessages');
    chatInput = document.getElementById('chatInput');
    sendButton = document.getElementById('sendButton');
    totalCourses = document.getElementById('totalCourses');
    courseTitles = document.getElementById('courseTitles');
    
    document.getElementById('newChatBtn').addEventListener('click', createNewSession);
    setupEventListeners();
    createNewSession();
    loadCourseStats();
});

// Event Listeners
function setupEventListeners() {
    // Chat functionality
    sendButton.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    
    
    // Suggested questions
    document.querySelectorAll('.suggested-item').forEach(button => {
        button.addEventListener('click', (e) => {
            const question = e.target.getAttribute('data-question');
            chatInput.value = question;
            sendMessage();
        });
    });
}


// Chat Functions
async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Disable input
    chatInput.value = '';
    chatInput.disabled = true;
    sendButton.disabled = true;

    // Add user message
    addMessage(query, 'user');

    // Add loading message - create a unique container for it
    const loadingMessage = createLoadingMessage();
    chatMessages.appendChild(loadingMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const response = await fetch(`${API_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                session_id: currentSessionId
            })
        });

        if (!response.ok) throw new Error('Query failed');

        const data = await response.json();
        
        // Update session ID if new
        if (!currentSessionId) {
            currentSessionId = data.session_id;
        }

        // Replace loading message with response
        loadingMessage.remove();
        addMessage(data.answer, 'assistant', data.sources);

    } catch (error) {
        // Replace loading message with error
        loadingMessage.remove();
        addMessage(`Error: ${error.message}`, 'assistant');
    } finally {
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatInput.focus();
    }
}

function createLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
        <div class="message-content">
            <div class="loading">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    return messageDiv;
}

function addMessage(content, type, sources = null, isWelcome = false) {
    const messageId = Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}${isWelcome ? ' welcome-message' : ''}`;
    messageDiv.id = `message-${messageId}`;
    
    // Convert markdown to HTML for assistant messages
    const displayContent = type === 'assistant' ? marked.parse(content) : escapeHtml(content);
    
    let html = `<div class="message-content">${displayContent}</div>`;
    
    if (sources && sources.length > 0) {
        html += `
            <details class="sources-collapsible">
                <summary class="sources-header">Sources</summary>
                <div class="sources-content">${sources.map(s => {
                    if (s.url) {
                        return `<a href="${s.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.label)}</a>`;
                    }
                    return `<span>${escapeHtml(s.label)}</span>`;
                }).join('')}</div>
            </details>
        `;
    }
    
    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageId;
}

// Helper function to escape HTML for user messages
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Removed removeMessage function - no longer needed since we handle loading differently

async function createNewSession() {
    if (currentSessionId) {
        try {
            await fetch(`${API_URL}/session/${currentSessionId}`, { method: 'DELETE' });
        } catch (e) {
            // best-effort cleanup, ignore errors
        }
    }
    currentSessionId = null;
    chatMessages.innerHTML = '';
    addMessage('Welcome to the Course Materials Assistant! I can help you with questions about courses, lessons and specific content. What would you like to know?', 'assistant', null, true);
}

// Load course statistics
async function loadCourseStats() {
    try {
        console.log('Loading course stats...');
        const response = await fetch(`${API_URL}/courses`);
        if (!response.ok) throw new Error('Failed to load course stats');
        
        const data = await response.json();
        console.log('Course data received:', data);
        
        // Update stats in UI
        if (totalCourses) {
            totalCourses.textContent = data.total_courses;
        }
        
        // Update course titles
        if (courseTitles) {
            if (data.course_titles && data.course_titles.length > 0) {
                courseTitles.innerHTML = data.course_titles
                    .map(title => `<div class="course-title-item">${title}</div>`)
                    .join('');
            } else {
                courseTitles.innerHTML = '<span class="no-courses">No courses available</span>';
            }
        }
        
    } catch (error) {
        console.error('Error loading course stats:', error);
        // Set default values on error
        if (totalCourses) {
            totalCourses.textContent = '0';
        }
        if (courseTitles) {
            courseTitles.innerHTML = '<span class="error">Failed to load courses</span>';
        }
    }
}