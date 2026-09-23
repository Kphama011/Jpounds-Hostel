let selectedRoom = null;
let selectedBeds = [];
let availableBeds = {};
let availabilityRequest = 0;

async function loadAvailability() {
    const checkIn = document.getElementById("checkIn")?.value;
    const checkOut = document.getElementById("checkOut")?.value;
    if (!checkIn || !checkOut || checkIn >= checkOut) return;

    const requestId = ++availabilityRequest;
    const response = await fetch(`/api/availability?check_in=${encodeURIComponent(checkIn)}&check_out=${encodeURIComponent(checkOut)}`);
    const result = await response.json();
    if (requestId !== availabilityRequest || !response.ok) return;

    availableBeds = Object.fromEntries(
        result.rooms.map((room) => [room.id, room.available_beds])
    );
    document.querySelectorAll(".room-card").forEach((element) => {
        const room = Number(element.id.replace("room", ""));
        element.hidden = !(availableBeds[room]?.length);
        element.classList.remove("selected-room");
    });

    if (selectedRoom !== null && !availableBeds[selectedRoom]?.length) {
        selectedRoom = null;
        selectedBeds = [];
        document.getElementById("bedSection").style.display = "none";
    } else if (selectedRoom !== null) {
        updateBeds();
    }
}

function selectRoom(room) {
    for (let i = 1; i <= 9; i++) {
        const roomElement = document.getElementById("room" + i);
        if (roomElement) roomElement.classList.remove("selected-room");
    }

    selectedRoom = room;
    selectedBeds = [];

    const selectedRoomElement = document.getElementById("room" + room);
    if (selectedRoomElement) selectedRoomElement.classList.add("selected-room");

    const bedSection = document.getElementById("bedSection");
    if (bedSection) bedSection.style.display = "block";

    const limit = availableBeds[room]?.length || 0;
    const roomTitle = document.getElementById("roomTitle");
    if (roomTitle) roomTitle.innerHTML = `Step 2: Select Beds in Room ${room} (Choose ${limit})`;

    updateBeds();
}

function updateBeds() {
    const visibleBeds = selectedRoom === null ? [] : (availableBeds[selectedRoom] || []);

    ["A1", "A2", "B1", "B2"].forEach((bed) => {
        const element = document.getElementById(bed);
        if (!element) return;

        const isVisible = visibleBeds.includes(bed);
        element.style.display = isVisible ? "block" : "none";
        element.classList.remove("selected-bed", "booked-bed");
    });
}

function selectBed(bed) {
    if (selectedRoom === null) {
        alert("Please select a room first.");
        return;
    }

    if (!availableBeds[selectedRoom]?.includes(bed)) return;

    const element = document.getElementById(bed);
    if (!element) return;

    if (selectedBeds.includes(bed)) {
        selectedBeds = selectedBeds.filter((item) => item !== bed);
        element.classList.remove("selected-bed");
        return;
    }

    const limit = availableBeds[selectedRoom]?.length || 0;
    if (selectedBeds.length < limit) {
        selectedBeds.push(bed);
        element.classList.add("selected-bed");
    } else {
        alert("This room allows only " + limit + " bed selections.");
    }
}

async function bookRoom() {
    const name = document.getElementById("guestName").value;
    const email = document.getElementById("guestEmail").value;
    const checkIn = document.getElementById("checkIn").value;
    const checkOut = document.getElementById("checkOut").value;
    const payment = document.getElementById("paymentMethod").value;
    const message = document.getElementById("message");

    if (selectedRoom === null) {
        message.textContent = "Please select a room.";
        message.style.color = "red";
        return;
    }

    if (selectedBeds.length === 0) {
        message.textContent = "Please select at least one bed.";
        message.style.color = "red";
        return;
    }

    if (!name || !email) {
        message.textContent = "Please enter your name and email.";
        message.style.color = "red";
        return;
    }

    if (!checkIn || !checkOut) {
        message.textContent = "Please select check-in and check-out dates.";
        message.style.color = "red";
        return;
    }

    if (!payment) {
        message.textContent = "Please select a payment method.";
        message.style.color = "red";
        return;
    }

    const response = await fetch("/api/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            guest_name: name,
            guest_email: email,
            room: selectedRoom,
            beds: selectedBeds,
            check_in: checkIn,
            check_out: checkOut,
            payment_method: payment
        })
    });

    const result = await response.json();

    if (!response.ok) {
        message.textContent = result.error || "Unable to save your booking.";
        message.style.color = "red";
        return;
    }

    message.textContent = result.message + " Room " + selectedRoom + " has been selected.";
    message.style.color = "green";
    selectedBeds = [];
    await loadAvailability();
}

function switchAuthMode(mode) {
    const loginForm = document.getElementById("loginForm");
    const signupForm = document.getElementById("signupForm");
    const forgotForm = document.getElementById("forgotForm");
    const resetForm = document.getElementById("resetForm");
    const loginTab = document.getElementById("loginTab");
    const signupTab = document.getElementById("signupTab");

    if (!loginForm || !signupForm) return;

    const isLogin = mode === "login";
    const isSignup = mode === "signup";
    const isForgot = mode === "forgot";
    const isReset = mode === "reset";

    loginForm.hidden = !isLogin;
    signupForm.hidden = !isSignup;
    forgotForm.hidden = !isForgot;
    resetForm.hidden = !isReset;

    loginTab.classList.toggle("active-auth-tab", isLogin || isForgot || isReset);
    signupTab.classList.toggle("active-auth-tab", isSignup);

    if (isLogin || isForgot || isReset) {
        signupTab.classList.remove("active-auth-tab");
    }
}

function showAuthMessage(message, isSuccess) {
    const element = document.getElementById("authMessage");
    if (!element) return;

    element.textContent = message;
    element.className = isSuccess ? "auth-message success" : "auth-message error";
}

async function signUp() {
    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim().toLowerCase();
    const password = document.getElementById("signupPassword").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (!name || !email || !password || !confirmPassword) {
        showAuthMessage("Please complete every field.", false);
        return;
    }

    if (!email.includes("@") || !email.includes(".")) {
        showAuthMessage("Please enter a valid email address.", false);
        return;
    }

    if (password.length < 6) {
        showAuthMessage("Your password must be at least 6 characters.", false);
        return;
    }

    if (password !== confirmPassword) {
        showAuthMessage("Your passwords do not match.", false);
        return;
    }

    const response = await fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password })
    });
    const result = await response.json();

    if (!response.ok) {
        showAuthMessage(result.error, false);
        return;
    }

    showAuthMessage(result.message, true);
    document.getElementById("loginEmail").value = email;
    switchAuthMode("login");
}

async function logIn() {
    const email = document.getElementById("loginEmail").value.trim().toLowerCase();
    const password = document.getElementById("loginPassword").value;

    if (!email || !password) {
        showAuthMessage("Please enter both email and password.", false);
        return;
    }

    const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
    });
    const result = await response.json();

    if (!response.ok) {
        showAuthMessage(result.error || "Invalid login details.", false);
        return;
    }

    updateAuthState();
    showAuthMessage("Welcome back, " + result.user.name + "!", true);
}

async function requestPasswordReset() {
    const email = document.getElementById("forgotEmail").value.trim().toLowerCase();
    if (!email) {
        showAuthMessage("Please enter your email address.", false);
        return;
    }

    const response = await fetch("/api/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
    });
    const result = await response.json();

    showAuthMessage(result.message || result.error || "Password reset request processed.", response.ok);
    if (response.ok) {
        document.getElementById("resetEmail").value = email;
        switchAuthMode("reset");
    }
}

async function resetPassword() {
    const email = document.getElementById("resetEmail").value.trim().toLowerCase();
    const token = document.getElementById("resetToken").value.trim();
    const password = document.getElementById("newPassword").value;
    const confirmPassword = document.getElementById("confirmResetPassword").value;

    if (!email || !token || !password || !confirmPassword) {
        showAuthMessage("Please complete all reset fields.", false);
        return;
    }

    if (password.length < 6) {
        showAuthMessage("Your new password must be at least 6 characters.", false);
        return;
    }

    if (password !== confirmPassword) {
        showAuthMessage("The new passwords do not match.", false);
        return;
    }

    const response = await fetch("/api/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, token, password })
    });
    const result = await response.json();

    showAuthMessage(result.message || result.error || "Password reset failed.", response.ok);
    if (response.ok) {
        switchAuthMode("login");
    }
}

async function logOut() {
    await fetch("/api/logout", { method: "POST" });
    updateAuthState();
    switchAuthMode("login");
    showAuthMessage("You have been logged out.", true);
}

async function updateAuthState() {
    const authForms = document.getElementById("authForms");
    const loggedIn = document.getElementById("loggedIn");
    const userName = document.getElementById("userName");

    if (!authForms || !loggedIn) return;

    const response = await fetch("/api/session");
    const result = await response.json();

    if (result.user) {
        authForms.hidden = true;
        loggedIn.hidden = false;
        userName.textContent = result.user.name;
    } else {
        authForms.hidden = false;
        loggedIn.hidden = true;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    updateAuthState();
    document.getElementById("checkIn")?.addEventListener("change", loadAvailability);
    document.getElementById("checkOut")?.addEventListener("change", loadAvailability);
});