"""Normalized rotating-frame CR3BP equations and Jacobi integral.

Coordinates are barycentric and normalized so the primary separation, total
mass, and angular frequency are unity. State order is (x, y, z, vx, vy, vz).
The model is idealized and does not include finite-mass third-body feedback,
non-circular primaries, perturbing bodies, or control acceleration.
"""

import math
from dataclasses import dataclass
from typing import cast


State = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class CR3BPDynamics:
    """Circular restricted three-body dynamics in normalized units."""

    mass_parameter: float
    singularity_tolerance: float = 1.0e-12

    def __post_init__(self) -> None:
        if not math.isfinite(self.mass_parameter) or not 0.0 < self.mass_parameter < 1.0:
            raise ValueError("mass_parameter must be finite and strictly between 0 and 1.")
        if (
            not math.isfinite(self.singularity_tolerance)
            or self.singularity_tolerance <= 0.0
        ):
            raise ValueError("singularity_tolerance must be finite and positive.")

    def effective_potential(self, x: float, y: float, z: float) -> float:
        """Return Ω = (x²+y²)/2 + (1-μ)/r1 + μ/r2."""
        self._validate_position(x, y, z)
        mu = self.mass_parameter
        r1, r2 = self._distances(x, y, z)
        return 0.5 * (x * x + y * y) + (1.0 - mu) / r1 + mu / r2

    def acceleration(self, x: float, y: float, z: float, vx: float, vy: float) -> tuple[float, float, float]:
        """Return rotating-frame accelerations including Coriolis terms."""
        self._validate_position(x, y, z)
        if not all(math.isfinite(value) for value in (vx, vy)):
            raise ValueError("Velocity components must be finite.")
        mu = self.mass_parameter
        r1, r2 = self._distances(x, y, z)
        r1_cubed = r1**3
        r2_cubed = r2**3
        primary = (1.0 - mu) / r1_cubed
        secondary = mu / r2_cubed
        omega_x = x - primary * (x + mu) - secondary * (x - 1.0 + mu)
        omega_y = y - (primary + secondary) * y
        omega_z = -(primary + secondary) * z
        return 2.0 * vy + omega_x, -2.0 * vx + omega_y, omega_z

    def rhs(self, state: State) -> State:
        """Evaluate the six-dimensional first-order state derivative."""
        self._validate_state(state)
        x, y, z, vx, vy, vz = state
        ax, ay, az = self.acceleration(x, y, z, vx, vy)
        return vx, vy, vz, ax, ay, az

    def jacobi_constant(self, state: State) -> float:
        """Return C = 2Ω - (vx² + vy² + vz²), conserved by ideal CR3BP flow."""
        self._validate_state(state)
        x, y, z, vx, vy, vz = state
        omega = self.effective_potential(x, y, z)
        return 2.0 * omega - (vx * vx + vy * vy + vz * vz)

    def propagate_rk4(self, initial_state: State, duration: float, steps: int) -> tuple[State, ...]:
        """Propagate with classical fixed-step RK4; includes the initial state."""
        self._validate_state(initial_state)
        if not math.isfinite(duration) or duration <= 0.0:
            raise ValueError("duration must be finite and positive.")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
            raise ValueError("steps must be a positive integer.")

        step_size = duration / steps
        state = initial_state
        trajectory = [state]
        for _ in range(steps):
            k1 = self.rhs(state)
            k2 = self.rhs(self._combine(state, k1, 0.5 * step_size))
            k3 = self.rhs(self._combine(state, k2, 0.5 * step_size))
            k4 = self.rhs(self._combine(state, k3, step_size))
            state = cast(
                State,
                tuple(
                    value + (step_size / 6.0) * (a + 2.0 * b + 2.0 * c + d)
                    for value, a, b, c, d in zip(state, k1, k2, k3, k4, strict=True)
                ),
            )
            self._validate_state(state)
            trajectory.append(state)
        return tuple(trajectory)

    def _distances(self, x: float, y: float, z: float) -> tuple[float, float]:
        mu = self.mass_parameter
        r1 = math.sqrt((x + mu) ** 2 + y * y + z * z)
        r2 = math.sqrt((x - 1.0 + mu) ** 2 + y * y + z * z)
        if r1 <= self.singularity_tolerance or r2 <= self.singularity_tolerance:
            raise ValueError("State is at or too close to a primary singularity.")
        return r1, r2

    def _validate_position(self, x: float, y: float, z: float) -> None:
        if not all(math.isfinite(value) for value in (x, y, z)):
            raise ValueError("Position components must be finite.")
        self._distances(x, y, z)

    @staticmethod
    def _validate_state(state: State) -> None:
        if len(state) != 6 or not all(math.isfinite(value) for value in state):
            raise ValueError("State must contain six finite components.")

    @staticmethod
    def _combine(state: State, derivative: State, scale: float) -> State:
        return tuple(
            value + scale * delta
            for value, delta in zip(state, derivative, strict=True)
        )  # type: ignore[return-value]
