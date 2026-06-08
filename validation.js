const form = document.getElementById("interestForm");
const clearButton = document.getElementById("clearForm");
const successMessage = document.getElementById("formSuccess");

const fieldRules = {
  fullName: (value) => {
    if (!value.trim()) return "Please enter your full name.";
    if (value.trim().length < 3) return "Full name must contain at least 3 characters.";
    return "";
  },
  email: (value) => {
    if (!value.trim()) return "Please provide your email address.";
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    if (!emailRegex.test(value.trim())) return "Enter a valid email address, for example name@domain.com.";
    return "";
  },
  phone: (value) => {
    if (!value.trim()) return "Please provide a phone number.";
    const phoneRegex = /^[+()\-\s\d]{7,20}$/;
    if (!phoneRegex.test(value.trim())) return "Use 7 to 20 digits and valid symbols such as +, -, or parentheses.";
    return "";
  },
  country: (value) => {
    if (!value) return "Please select the country of interest.";
    return "";
  },
  city: (value) => {
    if (!value.trim()) return "Please enter the city you are targeting.";
    if (value.trim().length < 2) return "City name must contain at least 2 characters.";
    return "";
  },
  experienceYears: (value) => {
    if (value === "") return "Please enter your years of business experience.";
    const years = Number(value);
    if (Number.isNaN(years) || years < 0) return "Years of experience must be 0 or greater.";
    return "";
  },
  locationType: (value) => {
    if (!value) return "Please choose a preferred location type.";
    return "";
  },
  investment: (value) => {
    if (value === "") return "Please enter your available investment range in USD.";
    const amount = Number(value);
    if (Number.isNaN(amount) || amount < 0) return "Investment amount must be 0 or greater.";
    if (amount < 50000) return "Minimum suggested investment is USD 50,000 for initial consideration.";
    return "";
  },
  referralSource: (value) => {
    if (!value) return "Please tell us how you heard about Brasaland.";
    return "";
  },
  message: (value) => {
    if (!value.trim()) return "Please share your motivation for partnering with Brasaland.";
    if (value.trim().length < 20) return "Message must contain at least 20 characters.";
    return "";
  },
};

function setFieldState(field, message) {
  const errorElement = document.getElementById(`${field.id}Error`);
  if (!errorElement) return;

  field.classList.remove("border-red-500", "ring-red-200", "bg-red-50", "border-emerald-500", "ring-emerald-200", "bg-emerald-50", "ring-2");

  if (message) {
    field.setAttribute("aria-invalid", "true");
    field.classList.add("border-red-500", "ring-2", "ring-red-200", "bg-red-50");
    errorElement.textContent = message;
    errorElement.classList.remove("hidden");
  } else {
    field.setAttribute("aria-invalid", "false");
    field.classList.add("border-emerald-500", "ring-2", "ring-emerald-200", "bg-emerald-50");
    errorElement.textContent = "";
    errorElement.classList.add("hidden");
  }
}

function validateField(field) {
  const validate = fieldRules[field.id];
  if (!validate) return true;

  const message = validate(field.value);
  setFieldState(field, message);
  return message === "";
}

function resetFieldState(field) {
  const errorElement = document.getElementById(`${field.id}Error`);
  field.removeAttribute("aria-invalid");
  field.classList.remove("border-red-500", "ring-red-200", "bg-red-50", "border-emerald-500", "ring-emerald-200", "bg-emerald-50", "ring-2");
  field.classList.add("border-stone-300");

  if (errorElement) {
    errorElement.textContent = "";
    errorElement.classList.add("hidden");
  }
}

if (form) {
  const fields = Array.from(form.querySelectorAll(".field"));

  fields.forEach((field) => {
    const eventName = field.tagName === "SELECT" ? "change" : "input";
    field.addEventListener(eventName, () => {
      validateField(field);
      if (successMessage) successMessage.classList.add("hidden");
    });

    field.addEventListener("blur", () => {
      validateField(field);
    });
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const invalidFields = fields.filter((field) => !validateField(field));

    if (invalidFields.length > 0) {
      if (successMessage) successMessage.classList.add("hidden");
      invalidFields[0].focus();
      return;
    }

    if (successMessage) {
      successMessage.classList.remove("hidden");
      successMessage.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    form.reset();
    fields.forEach((field) => resetFieldState(field));
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      form.reset();
      fields.forEach((field) => resetFieldState(field));
      if (successMessage) successMessage.classList.add("hidden");
    });
  }
}
