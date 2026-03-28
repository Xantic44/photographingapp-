// Read page elements once so we can reuse them in functions.
const loadBtn = document.getElementById("loadBtn");
const loadResult = document.getElementById("loadResult");
const noteInput = document.getElementById("noteInput");
const saveNoteBtn = document.getElementById("saveNoteBtn");
const noteStatus = document.getElementById("noteStatus");
const notesList = document.getElementById("notesList");

// Prevent user-entered text from being interpreted as HTML.
function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// GET /api/hello -> show the latest note as a simple message.
loadBtn.addEventListener("click", async () => {
  loadResult.textContent = "Loading...";

  try {
    const response = await fetch("/api/hello");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    loadResult.textContent = data.message;
  } catch (error) {
    loadResult.textContent = "Could not load latest note.";
    console.error("Load message failed:", error);
  }
});

// POST /api/notes -> save user note into SQLite.
saveNoteBtn.addEventListener("click", async () => {
  const noteText = noteInput.value.trim();

  // Basic input validation.
  if (!noteText) {
    noteStatus.textContent = "Please enter a note first.";
    return;
  }

  noteStatus.textContent = "Saving...";

  try {
    const response = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: noteText }),
    });

    const data = await response.json();
    if (!response.ok) {
      noteStatus.textContent = data.error || "Failed to save note.";
      return;
    }

    noteStatus.textContent = data.message || "Note saved!";
    noteInput.value = "";

    // Reload the list so the new note appears immediately.
    refreshNotesList();
  } catch (error) {
    noteStatus.textContent = "Could not reach server.";
    console.error("Save note failed:", error);
  }
});

// GET /api/notes -> fetch and render latest notes in the list UI.
async function refreshNotesList() {
  try {
    const response = await fetch("/api/notes");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const notes = data.notes || [];

    if (notes.length === 0) {
      notesList.innerHTML = `
        <li class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-stone-600">
          No notes yet. Add your first one above.
        </li>
      `;
      return;
    }

    notesList.innerHTML = notes
      .map(
        (note) => `
          <li class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
            <span class="font-semibold text-rose-700">#${note.id}</span>
            <span class="text-stone-700"> ${escapeHtml(note.text)}</span>
          </li>
        `
      )
      .join("");
  } catch (error) {
    notesList.innerHTML = `
      <li class="rounded-xl border border-red-300 bg-red-50 px-3 py-2 text-red-700">
        Could not load notes.
      </li>
    `;
    console.error("Refresh notes failed:", error);
  }
}

// Load notes once when the page first opens.
refreshNotesList();
