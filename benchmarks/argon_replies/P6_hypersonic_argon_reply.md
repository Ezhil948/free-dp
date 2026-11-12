prompt 1:### 1. Governing Conservation Equations & Thermochemical Formulation

The hypersonic flow of a 5-species reacting air mixture ($\mathcal{S} = \{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}\}$) in two-temperature ($T, T_v$) thermal non-equilibrium is governed by the multi-component compressible Navier-Stokes equations. Here, $T$ represents the translational-rotational temperature and $T_v$ represents the vibrational-electronic temperature.

#### Species Continuity, Momentum, and Energy Conservation

**Species Continuity:**

$$\frac{\partial (\rho Y_s)}{\partial t} + \nabla \cdot (\rho \mathbf{u} Y_s + \mathbf{J}_s) = \dot{\omega}_s, \quad s \in \mathcal{S}$$

where $\rho = \sum_{s \in \mathcal{S}} \rho_s$ is the mixture density, $Y_s = \rho_s / \rho$ is the mass fraction of species $s$, $\mathbf{u}$ is the mass-averaged bulk velocity vector, and $\dot{\omega}_s$ is the net mass production rate per unit volume due to chemical reactions ($\sum_{s \in \mathcal{S}} \dot{\omega}_s = 0$). The diffusive mass flux $\mathbf{J}_s$ is modeled via modified Fick's law with a mass-conservation correction:

$$\mathbf{J}_s = -\rho D_s \nabla Y_s + Y_s \rho \sum_{k \in \mathcal{S}} D_k \nabla Y_k$$

**Mixture Momentum Conservation:**

$$\frac{\partial (\rho \mathbf{u})}{\partial t} + \nabla \cdot (\rho \mathbf{u} \otimes \mathbf{u} + p \mathbf{I} - \boldsymbol{\tau}) = \mathbf{0}$$

where the thermodynamic pressure follows Dalton's Law of partial pressures:

$$p = \sum_{s \in \mathcal{S}} p_s = \sum_{s \in \mathcal{S}} \rho_s \frac{R_u}{M_s} T = \rho \bar{R} T$$

with universal gas constant $R_u = 8.31446 \text{ J/(mol}\cdot\text{K)}$ and species molar mass $M_s$. The viscous stress tensor under Stokes' hypothesis is:

$$\boldsymbol{\tau} = \mu \left( \nabla \mathbf{u} + (\nabla \mathbf{u})^T - \frac{2}{3} (\nabla \cdot \mathbf{u}) \mathbf{I} \right)$$

**Total Energy Conservation:**

$$\frac{\partial (\rho E)}{\partial t} + \nabla \cdot \left( (\rho E + p)\mathbf{u} - \boldsymbol{\tau} \cdot \mathbf{u} + \mathbf{q}_{tr} + \mathbf{q}_v + \sum_{s \in \mathcal{S}} h_s \mathbf{J}_s \right) = 0$$

where total specific energy is $E = e + \frac{1}{2}\Vert{}\mathbf{u}\Vert{}^2$, mixture internal energy is $e = \sum_{s \in \mathcal{S}} Y_s e_s(T, T_v)$, and species specific enthalpy is $h_s = e_s + \frac{R_u}{M_s}T$. The heat flux vectors are governed by Fourier's law for each thermal mode:

$$\mathbf{q}_{tr} = -\kappa_{tr} \nabla T, \quad \mathbf{q}_v = -\kappa_v \nabla T_v$$

**Vibrational-Electronic Energy Conservation:**
Let $\mathcal{M} = \{\text{N}_2, \text{O}_2, \text{NO}\}$ denote the subset of diatomic molecular species possessing vibrational modes:

$$\frac{\partial (\rho e_v)}{\partial t} + \nabla \cdot \left( \rho \mathbf{u} e_v + \mathbf{q}_v + \sum_{s \in \mathcal{M}} e_{v,s} \mathbf{J}_s \right) = \dot{Q}_{V-T} + \dot{Q}_{chem,v}$$

Ignoring electronic excitation for the 5-species neutral regime, the species internal energy decomposes into translational, rotational, vibrational, and formation enthalpy ($\Delta h_{f,s}^0$) modes:

$$e_s(T, T_v) = e_{tr,s}(T) + e_{rot,s}(T) + e_{v,s}(T_v) + \Delta h_{f,s}^0$$

- For monatomic species ($s \in \{\text{N}, \text{O}\}$): $e_{tr,s}(T) = \frac{3}{2}\frac{R_u}{M_s}T$, $e_{rot,s} = 0$, $e_{v,s} = 0$.
- For diatomic species ($s \in \mathcal{M}$): $e_{tr,s}(T) = \frac{3}{2}\frac{R_u}{M_s}T$, $e_{rot,s}(T) = \frac{R_u}{M_s}T$, and the harmonic oscillator vibrational energy is:

$$e_{v,s}(T_v) = \frac{R_u}{M_s} \frac{\Theta_{v,s}}{\exp(\Theta_{v,s}/T_v) - 1}$$

where $\Theta_{v,s}$ is the characteristic vibrational temperature ($\Theta_{v,\text{N}_2} = 3395\text{ K}$, $\Theta_{v,\text{O}_2} = 2239\text{ K}$, $\Theta_{v,\text{NO}} = 2817\text{ K}$). The total mixture vibrational energy per unit mass is $e_v = \sum_{s \in \mathcal{M}} Y_s e_{v,s}(T_v)$. The chemical-vibrational source term under the non-preferential dissociation model is $\dot{Q}_{chem,v} = \sum_{s \in \mathcal{M}} \dot{\omega}_s e_{v,s}(T_v)$.

---

#### Vibrational-Translational Energy Exchange ($\dot{Q}_{V-T}$)

The rate of energy exchange between translational-rotational and vibrational modes is modeled via the **Landau-Teller** formulation:

$$\dot{Q}_{V-T} = \sum_{s \in \mathcal{M}} \rho_s \frac{e_{v,s}^*(T) - e_{v,s}(T_v)}{\tau_s}$$

where $e_{v,s}^*(T) = \frac{R_u}{M_s} \frac{\Theta_{v,s}}{\exp(\Theta_{v,s}/T) - 1}$ is the equilibrium vibrational energy evaluated at the translational temperature $T$, and $\tau_s$ is the effective relaxation time for molecule $s$.

1. **Millikan-White Collision Relaxation Time ($\tau_{s,r}^{MW}$):**
   For collisions between vibrating molecule $s \in \mathcal{M}$ and collision partner $r \in \mathcal{S}$, the semi-empirical correlation of Millikan & White (1963) gives the relaxation time (in seconds, with pressure $p_{\text{atm}} = p / 101325$ in atmospheres):

$$\tau_{s,r}^{MW} = \frac{1}{p_{\text{atm}}} \exp \left[ A_{s,r} \left( T^{-1/3} - B_{s,r} \right) - 18.42 \right]$$

where the reduced molecular weight $\mu_{s,r}$ (in g/mol) and constants $A_{s,r}, B_{s,r}$ are:

$$\mu_{s,r} = \frac{M_s M_r}{M_s + M_r}, \quad A_{s,r} = 1.16 \times 10^{-3} \mu_{s,r}^{1/2} \Theta_{v,s}^{4/3}, \quad B_{s,r} = 0.015 \mu_{s,r}^{1/4}$$

The mixture-averaged Millikan-White relaxation time for species $s$ is obtained via molar-weighted harmonic averaging over all collision partners $r \in \mathcal{S}$:

$$\tau_s^{MW} = \left( \sum_{r \in \mathcal{S}} \frac{X_r}{\tau_{s,r}^{MW}} \right)^{-1}, \quad X_r = \frac{Y_r / M_r}{\sum_{k \in \mathcal{S}} Y_k / M_k}$$

2. **Park's High-Temperature Limiting Cross-Section Correction ($\tau_s^P$):**
   At extreme post-shock temperatures ($T > 8000\text{ K}$), the Millikan-White formula predicts an unphysically rapid relaxation rate that exceeds the hard-sphere collision frequency. Park (1993) resolved this by adding a diffusive limiting collision time $\tau_s^P$ in series:

$$\tau_s = \tau_s^{MW} + \tau_s^P$$

$$\tau_s^P = \frac{1}{n \sigma_v \bar{c}_s}$$

where $n = \sum_{r \in \mathcal{S}} \frac{\rho_r N_A}{M_r}$ is the total mixture number density ($\text{m}^{-3}$), $\bar{c}_s = \sqrt{\frac{8 k_B T}{\pi m_s}} = \sqrt{\frac{8 R_u T}{\pi M_s}}$ is the mean thermal molecular speed of species $s$, and $\sigma_v$ is the limiting vibrational cross-section:

$$\sigma_v = \sigma_v^0 \left( \frac{50000}{T} \right)^2 \quad \text{with } \sigma_v^0 \approx 10^{-21}\text{ m}^2$$

---

### 2. Reaction Rates & Two-Temperature Governing Formulation

#### Park (1993) 17-Reaction Mechanism for 5-Species Air

The chemical kinetics of the 5-species air mixture consist of 15 thermal dissociation-recombination reactions (3 diatomic molecules colliding with each of the 5 mixture species) and 2 Zeldovich bimolecular exchange reactions:

1. $\text{N}_2 + M \rightleftharpoons 2\text{N} + M \quad (M \in \{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}\}, \text{ 5 reactions})$
2. $\text{O}_2 + M \rightleftharpoons 2\text{O} + M \quad (M \in \{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}\}, \text{ 5 reactions})$
3. $\text{NO} + M \rightleftharpoons \text{N} + \text{O} + M \quad (M \in \{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}\}, \text{ 5 reactions})$
4. $\text{N}_2 + \text{O} \rightleftharpoons \text{NO} + \text{N} \quad (\text{Zeldovich Exchange 1})$
5. $\text{NO} + \text{O} \rightleftharpoons \text{O}_2 + \text{N} \quad (\text{Zeldovich Exchange 2})$

#### Controlling Temperature & Law of Mass Action

In a two-temperature gas, molecules in higher vibrational states dissociate far more readily than ground-state molecules (**vibration-dissociation coupling**). Park accounts for this by evaluating forward dissociation rates at a geometric mean effective temperature $T_a$:

$$T_a = T^q T_v^{1-q}$$

- **Exact Park (1993) exponent:** For all third-body dissociation reactions (Reactions 1–15), **$q = 0.5$** (or $q = 0.7$ in earlier 1985–1990 variants; $q = 0.5$ is the canonical standard for the 1993 model), yielding $T_a = \sqrt{T T_v}$.
- **Exchange & Recombination reactions:** For Zeldovich exchange reactions (Reactions 16–17) and all backward recombination rates, the controlling temperature depends solely on the translational-rotational temperature ($q = 1.0$, so $T_a = T$).

For a general elementary reaction $r \in \{1, \dots, 17\}$:

$$\sum_{s \in \mathcal{S}} \nu_{s,r}' \mathcal{X}_s \underset{k_{b,r}}{\overset{k_{f,r}}{\rightleftharpoons}} \sum_{s \in \mathcal{S}} \nu_{s,r}'' \mathcal{X}_s$$

The forward rate coefficient follows the modified Arrhenius form:

$$k_{f,r}(T_a) = C_{f,r} T_a^{\eta_r} \exp\left( -\frac{\Theta_{d,r}}{T_a} \right)$$

While the forward dissociation rate is governed by $T_a$, three-body recombination collisions depend purely on the translational kinetic energy of colliding atoms. Thus, the backward rate coefficient $k_{b,r}$ is evaluated strictly at $T$ via the principle of detailed balance:

$$k_{b,r}(T) = \frac{k_{f,r}(T)}{K_{c,r}(T)}$$

The net mass production rate $\dot{\omega}_s$ for species $s$ is given by the **Law of Mass Action**:

$$\dot{\omega}_s = M_s \sum_{r=1}^{17} (\nu_{s,r}'' - \nu_{s,r}') \left[ k_{f,r}(T_{a,r}) \prod_{k \in \mathcal{S}} \left( \frac{\rho_k}{M_k} \right)^{\nu_{k,r}'} - k_{b,r}(T) \prod_{k \in \mathcal{S}} \left( \frac{\rho_k}{M_k} \right)^{\nu_{k,r}''} \right]$$

#### Statistical Mechanics Derivation of Equilibrium Constant $K_{c,r}(T)$

From statistical thermodynamics, the concentration equilibrium constant $K_{c,r}(T)$ for reaction $r$ is determined directly from the molecular canonical partition functions $Q_s(V,T)$ and zero-point energy differences $\Delta \epsilon_{0,r} = \sum_{s \in \mathcal{S}} (\nu_{s,r}'' - \nu_{s,r}') \epsilon_{0,s}$:

$$K_{c,r}(T) = \left( \frac{1}{N_A} \right)^{\Delta \nu_r} \prod_{s \in \mathcal{S}} \left( \frac{Q_s(V,T)}{V} \right)^{\nu_{s,r}'' - \nu_{s,r}'} \exp\left( -\frac{\Delta \epsilon_{0,r}}{k_B T} \right)$$

where $\Delta \nu_r = \sum_{s \in \mathcal{S}} (\nu_{s,r}'' - \nu_{s,r}')$. Factoring the partition function per unit volume into translational, rotational, vibrational, and electronic components:

$$\frac{Q_s(V,T)}{V} = \underbrace{\left( \frac{2\pi m_s k_B T}{h_{\text{Planck}}^2} \right)^{3/2}}_{Q_{tr,s}/V} \cdot \underbrace{\frac{T}{\sigma_{sym,s} \Theta_{rot,s}}}_{Q_{rot,s} \text{ (diatomic)}} \cdot \underbrace{\frac{1}{1 - \exp(-\Theta_{v,s}/T)}}_{Q_{vib,s} \text{ (diatomic)}} \cdot \underbrace{\sum_{i} g_{i,s} \exp\left(-\frac{\theta_{el,i,s}}{T}\right)}_{Q_{el,s}}$$

where $\sigma_{sym,s} = 2$ for homonuclear diatomics ($\text{N}_2, \text{O}_2$), $\sigma_{sym,s} = 1$ for heteronuclear diatomics ($\text{NO}$), and $Q_{rot,s} = Q_{vib,s} = 1$ for monatomic species ($\text{N}, \text{O}$). Equivalently, in continuum thermodynamics via minimization of Gibbs free energy ($G_s^\circ(T) = H_s^\circ(T) - T S_s^\circ(T)$ at standard reference pressure $p^\circ = 1\text{ bar}$):

$$K_{c,r}(T) = \left( \frac{p^\circ}{R_u T} \right)^{\Delta \nu_r} \exp\left( -\sum_{s \in \mathcal{S}} \frac{(\nu_{s,r}'' - \nu_{s,r}') G_s^\circ(T)}{R_u T} \right)$$

---

### 3. 1D Normal Shock Jump Conditions & State Proofs

Consider a steady, 1D inviscid flow across a normal shock wave along the $x$-coordinate. Integrating the conservation equations across an infinitesimally thin control volume enclosing the shock front (where $\Delta x \to 0$) eliminates spatial integral source terms ($\int \dot{\omega}_s dx \to 0$, $\int \dot{Q}_{V-T} dx \to 0$), yielding the general **Rankine-Hugoniot jump relations**:

$$\rho_1 u_1 = \rho_2 u_2$$

$$\rho_1 u_1^2 + p_1 = \rho_2 u_2^2 + p_2$$

$$h_1 + \frac{1}{2}u_1^2 = h_2 + \frac{1}{2}u_2^2$$

where subscript $1$ denotes the upstream free-stream state ($\infty$) and subscript $2$ denotes a downstream state.

#### Mathematical Proof: Frozen Jump vs. Thermochemical Equilibrium State

The fundamental physical distinction between the immediate post-shock state ($2,f$) and the far-field downstream equilibrium state ($2,eq$) lies in the characteristic collision scales ($N_{\text{coll}}$) required to excite each internal mode:

- **Translational & Rotational modes:** Equilibrate within $O(1\text{–}5)$ molecular collisions (occurring entirely _inside_ the viscous shock thickness $\delta_s \sim O(\lambda_\infty) \approx 0.5\text{ mm}$ at $65\text{ km}$).
- **Vibrational excitation:** Requires $O(10^3\text{–}10^5)$ collisions ($\Delta x_{vib} \sim O(10^{-2})\text{ m}$).
- **Chemical dissociation:** Requires $O(10^5\text{–}10^7)$ collisions ($\Delta x_{chem} \sim O(10^{-1})\text{ m}$).

##### 1. Frozen Shock Jump State ($2,f$ at $x = 0^+$)

Across the thin shock front ($\Delta x \approx \delta_s$), residence time $\tau_{res} \sim \delta_s / u_1 \approx 10^{-7}\text{ s}$ is orders of magnitude shorter than $\tau_{vib}$ and $\tau_{chem}$. Therefore, across the discontinuity:

$$Y_{s,2f} = Y_{s,1} \quad \forall s \in \mathcal{S}, \qquad T_{v,2f} = T_{v,1} = T_1$$

Because only translational and rotational modes absorb the kinetic energy jump across the shock, the active specific heat ratio is constant at the diatomic translational-rotational value:

$$\gamma_f = \frac{c_{p,tr-rot}}{c_{v,tr-rot}} = \frac{\frac{7}{2}\bar{R}_1}{\frac{5}{2}\bar{R}_1} = 1.4$$

Because $e_{v,s}(T_{v,2f}) = e_{v,s}(T_1)$ and $\Delta h_{f,s}^0$ cancel identically on both sides of the enthalpy equation when $Y_{s,2f} = Y_{s,1}$, the enthalpy jump reduces to $c_{p,f}(T_{2f} - T_1) = \frac{1}{2}(u_1^2 - u_{2f}^2)$. Combining with mass and momentum conservation yields the exact closed-form frozen Rankine-Hugoniot relations:

$$\frac{\rho_{2f}}{\rho_1} = \frac{u_1}{u_{2f}} = \frac{(\gamma_f + 1) M_1^2}{(\gamma_f - 1) M_1^2 + 2}$$

$$\frac{p_{2f}}{p_1} = 1 + \frac{2\gamma_f}{\gamma_f + 1}(M_1^2 - 1)$$

$$\frac{T_{2f}}{T_1} = \left( \frac{p_{2f}}{p_1} \right) \left( \frac{\rho_1}{\rho_{2f}} \right) = \frac{\left[ 2\gamma_f M_1^2 - (\gamma_f - 1) \right] \left[ (\gamma_f - 1)M_1^2 + 2 \right]}{(\gamma_f + 1)^2 M_1^2}$$

For $M_1 = 14.5$, $T_1 = 233.3\text{ K}$, $p_1 = 10.93\text{ Pa}$, $\rho_1 = 1.63 \times 10^{-4}\text{ kg/m}^3$:

- $\rho_{2f} / \rho_1 = 5.7294 \implies \rho_{2f} = 9.339 \times 10^{-4}\text{ kg/m}^3$
- $p_{2f} / p_1 = 245.19 \implies p_{2f} = 2679.9\text{ Pa}$
- $T_{2f} / T_1 = 42.795 \implies T_{2f} = 9984.1\text{ K}$, while $T_{v,2f} = 233.3\text{ K}$.

##### 2. Thermochemical Equilibrium State ($2,eq$ as $x \to \infty$)

Far downstream of the shock, all relaxation source terms vanish ($\dot{Q}_{V-T} = 0$, $\dot{\omega}_s = 0$):

$$T_{v,2eq} = T_{2eq}, \qquad Y_{s,2eq} = Y_s^*(p_{2eq}, T_{2eq})$$

where $Y_s^*$ satisfies the nonlinear algebraic system of chemical equilibrium constants $K_{c,r}(T_{2eq})$. Expanding the enthalpy conservation equation between state $1$ and state $2,eq$:

$$\sum_{s \in \mathcal{S}} Y_{s,2eq} c_{p,tr-rot,s} T_{2eq} = h_1 + \frac{1}{2}(u_1^2 - u_{2eq}^2) - \underbrace{\sum_{s \in \mathcal{M}} Y_{s,2eq} e_{v,s}^*(T_{2eq})}_{\Delta h_{vib} > 0} - \underbrace{\sum_{s \in \mathcal{S}} (Y_{s,2eq} - Y_{s,1}) \Delta h_{f,s}^0}_{\Delta h_{chem} \gg 0}$$

Because dissociation of $\text{O}_2$ ($\Delta h_{f,\text{O}}^0 = 15.58\text{ MJ/kg}$) and $\text{N}_2$ ($\Delta h_{f,\text{N}}^0 = 33.63\text{ MJ/kg}$) is strongly endothermic ($\Delta h_{chem} \gg 0$) and vibrational excitation absorbs energy ($\Delta h_{vib} > 0$), and because $u_2^2 \ll u_1^2$ so $\frac{1}{2}(u_1^2 - u_{2eq}^2) \approx \frac{1}{2}(u_1^2 - u_{2f}^2) \approx \frac{1}{2}u_1^2$, subtracting the frozen enthalpy relation proves:

$$T_{2eq} \ll T_{2f}$$

Furthermore, in hypersonic flows ($M_1 \gg 1$), post-shock pressure is primarily determined by the momentum flux $\rho_1 u_1^2$:

$$p_2 = p_1 + \rho_1 u_1^2 \left( 1 - \frac{\rho_1}{\rho_2} \right)$$

Since $\rho_1 / \rho_2 \ll 1$, pressure changes only slightly during relaxation ($p_{2eq} \approx 1.12 \, p_{2f}$). Applying the equation of state $\rho = \frac{p}{Z \bar{R}_1 T}$ where $Z = \frac{\bar{M}_1}{\bar{M}_2} = \frac{\sum (Y_{s,2}/M_s)}{\sum (Y_{s,1}/M_s)} > 1$ is the compressibility factor (mole increase from dissociation):

$$\frac{\rho_{2eq}}{\rho_{2f}} = \left(\frac{p_{2eq}}{p_{2f}}\right) \left(\frac{T_{2f}}{T_{2eq}}\right) \frac{1}{Z_{2eq}}$$

Even though $Z_{2eq} > 1$, the massive drop in temperature ($T_{2f}/T_{2eq} \approx 2.5\text{–}3.0$) dominates over $Z_{2eq} \approx 1.3\text{–}1.6$, proving strictly that:

$$\rho_{2eq} \gg \rho_{2f} \quad \text{and} \quad u_{2eq} \ll u_{2f}$$

---

### 4. Adversarial Traps & Boundary Failure Modes

#### 1. The Equilibrium Fallacy: Heat Flux & Shock Stand-off Errors

Assuming either an equilibrium calorically/thermally adjusted specific heat $C_{p,eq}(T)$ or instantaneous local chemical equilibrium ($Y_s = Y_s^*(p,T)$) introduces severe errors in hypersonic blunt-body design:

- **Miscalculation of Shock Stand-off Distance ($\Delta_{so}$):**
  By mass conservation between the symmetry streamline and the body surface, the shock stand-off distance $\Delta_{so}$ on a blunt body of nose radius $R_N$ scales inversely with the average shock-layer density ratio (Lighthill's approximation):

$$\frac{\Delta_{so}}{R_N} \approx k \frac{\rho_\infty}{\bar{\rho}_{shock\_layer}}$$

If an equilibrium solver is used at high altitudes ($H = 65\text{ km}$, where Damköhler numbers $Da = \tau_{flow}/\tau_{chem} \sim O(1)$), it assumes instantaneous dissociation right behind the shock, jumping immediately to $\rho_{2eq} \approx 12\text{–}15 \rho_\infty$. In reality, a substantial portion of the shock layer remains in a finite-rate relaxation zone where $\rho(x)$ transitions gradually from $\rho_{2f} \approx 5.73 \rho_\infty$ toward $\rho_{2eq}$. Consequently, the equilibrium assumption **overpredicts shock-layer density** and **severely underpredicts shock stand-off distance $\Delta_{so}$** (often by $30\%\text{–}50\%$).

- **Overprediction of Peak Stagnation Heat Flux ($q_w$):**

1. _Using $C_p(T)$ without dissociation (Frozen Chemistry Fallacy):_ If a solver treats air as non-reacting with temperature-dependent $C_p(T)$, all kinetic energy $\frac{1}{2}u_\infty^2$ remains trapped as sensible thermal energy ($T_{stag} \approx 9000\text{ K}$ instead of $\sim 4000\text{ K}$), creating an artificially steep thermal gradient $\nabla T\vert{}_w$ and vastly overpredicting conductive heat flux $-\kappa \nabla T\vert{}_w$.
2. _Assuming Local Chemical Equilibrium (LCE) vs. Finite-Rate Non-Equilibrium:_ Under the LCE assumption, the total heat flux at the wall is given by resolving Fourier conduction and equilibrium species diffusion via an effective equilibrium conductivity $\kappa_{eff} = \kappa_{tr-v} + \sum_{s} \rho D_s h_s \frac{\partial Y_s^*(T)}{\partial T}$:

$$q_{w,LCE} = -\kappa_{eff} \frac{\partial T}{\partial n}\bigg\vert{}_w$$

Because the wall temperature is cold ($T_w \approx 1000\text{–}1500\text{ K}$), $Y_{\text{N}}^*(T_w) = Y_{\text{O}}^*(T_w) = 0$. Thus, an LCE solver forces **100% of dissociated N and O atoms to recombine within the gas phase just above the wall**, dumping their entire chemical formation enthalpy ($\Delta h_{f,\text{N}}^0, \Delta h_{f,\text{O}}^0$) directly into the boundary layer and onto the wall. In actual rarefied hypersonic flow at $65\text{ km}$, three-body gas-phase recombination ($\text{N} + \text{N} + M \to \text{N}_2 + M$, scaling as $\rho^2$) is **chemically frozen** inside the cool boundary layer due to low density. If the TPS surface has low catalytic efficiency (e.g., reaction-cured glass on Shuttle tiles), the atoms remain un-recombined at the wall, and the chemical energy is convected harmlessly downstream. Hence, LCE **severely overpredicts stagnation heat transfer** over real low-catalytic thermal protection systems.

---

#### 2. Model Scope & Ionization Boundaries ($M_\infty = 25$ Catastrophe)

The 5-species neutral air model ($\{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}\}$) is strictly valid only for flight velocities **$u_\infty \lesssim 8\text{ km/s}$** ($M_\infty \lesssim 24\text{–}25$ depending on altitude).

- **Exact Thresholds for $\text{NO}^+$ and $e^-$ Ionization:**
  The onset of weakly ionized plasma in air occurs via **associative ionization of nitric oxide**, which has the lowest ionization threshold energy among air species ($E_{ion,\text{NO}} = 9.26\text{ eV}$, corresponding to an activation temperature of $\Theta_{ion,\text{NO}} \approx 32000\text{ K}$ for the associative pathway $\text{N} + \text{O} \rightleftharpoons \text{NO}^+ + e^-$):
- **Temperature Threshold:** When translational temperature exceeds **$T \approx 4500\text{–}5000\text{ K}$**, trace associative ionization ($\text{N} + \text{O} \to \text{NO}^+ + e^-$) begins, producing electron number densities $n_e \sim 10^{18}\text{–}10^{19}\text{ m}^{-3}$ (sufficient to cause RF communications blackout).
- **Velocity Threshold:** At **$u_\infty \approx 5.0\text{–}5.5\text{ km/s}$** ($M_\infty \approx 16\text{–}18$), post-shock temperatures cross $5000\text{ K}$, making $\text{NO}^+$ and $e^-$ essential for electromagnetic/plasma modeling, though their mole fraction ($X_e \sim 10^{-4}$) only weakly perturbs bulk fluid thermodynamics.
- **Thermodynamic/Fluid Breakdown Threshold:** At **$u_\infty \ge 8.0\text{ km/s}$** ($M_\infty \ge 25$, where frozen shock temperatures exceed **$T_{2f} > 20000\text{ K}$** and equilibrium temperatures exceed **$T_{2eq} > 8000\text{ K}$**), direct electron-impact ionization of atomic nitrogen and oxygen ($\text{N} + e^- \rightleftharpoons \text{N}^+ + 2e^-$, $\Delta \epsilon = 14.53\text{ eV}$; $\text{O} + e^- \rightleftharpoons \text{O}^+ + 2e^-$, $\Delta \epsilon = 13.62\text{ eV}$) and associative ionization ($\text{N}+\text{N} \rightleftharpoons \text{N}_2^+ + e^-$) become major thermodynamic energy sinks, requiring an **11-species plasma model** ($\{\text{N}_2, \text{O}_2, \text{NO}, \text{N}, \text{O}, \text{N}_2^+, \text{O}_2^+, \text{NO}^+, \text{N}^+, \text{O}^+, e^-\}$).

- **Why a 5-Species Solver Catastrophically Fails at $M_\infty = 25$:**
  At $M_\infty = 25$ ($u_\infty \approx 7.67\text{ km/s}$ at $65\text{ km}$, or $>8\text{ km/s}$ in the mesosphere), the specific kinetic energy is $\frac{1}{2}u_\infty^2 \approx 29.4\text{ MJ/kg}$, yielding a frozen post-shock temperature of **$T_{2f} \approx 29,300\text{ K}$**. A 5-species solver fails catastrophically for four compounding reasons:

1. **Exhaustion of Endothermic Sinks:** Once $\text{O}_2$ and $\text{N}_2$ fully dissociate into $\text{N}$ and $\text{O}$, the 5-species model has **no remaining chemical endothermic sink** to absorb kinetic energy. Without the massive ionization enthalpies of $\text{N}^+$ ($100.2\text{ MJ/kg}$) and $\text{O}^+$ ($82.1\text{ MJ/kg}$) and bound-electronic excitation, post-shock temperature remains unphysically high.
2. **Thermodynamic Polynomial & Rate Divergence:** Standard NASA 7- or 9-coefficient thermodynamic polynomials for neutral species are only fitted up to $6000\text{ K}$ or $15000\text{ K}$; extrapolating them to $29,300\text{ K}$ causes negative specific heats or wild divergence in $K_c(T)$. Furthermore, Park's dissociation rates with negative temperature exponents ($\eta = -1.60$ for $\text{N}_2$, $\eta = -1.50$ for $\text{O}_2$) turn non-monotonic and artificially decrease at extreme temperatures.
3. **Omission of Ambipolar & Electron Transport:** Free electrons ($m_e \ll m_{\text{N}}$) have thermal velocities $\bar{c}_e = \sqrt{8k_B T_e / \pi m_e}$ over 160 times larger than heavy particles. Omitting electron thermal conductivity ($\kappa_e$) and ambipolar diffusion ($D_{amb} \approx 2 D_{ion}$) severely miscalculates boundary-layer thermal transport.
4. **Omission of Radiative Cooling:** Above $9000\text{ K}$, shock-layer radiative heat transfer ($\nabla \cdot \mathbf{q}_{rad}$) from electronic transitions of $\text{N}, \text{O}, \text{N}_2^+$ becomes comparable to convective heating, invalidating an adiabatic shock layer.

---

#### 3. Catalytic Wall Ambiguity & Goulard's Surface Recombination

At the solid vehicle wall (outward unit normal $\mathbf{n}$ pointing from the solid into the fluid), the net diffusive mass flux of species $s$ leaving the wall must balance the net heterogeneous catalytic creation/destruction rate $\dot{w}_{s,w}$ ($\text{kg/(m}^2\cdot\text{s)}$) on the surface:

$$\mathbf{J}_s \cdot \mathbf{n}\big|_w = -\rho_w D_{s,w} \frac{\partial Y_s}{\partial n}\bigg|_w = \dot{w}_{s,w}$$

The total convective + diffusive heat flux into the wall is:

$$q_w = \underbrace{\kappa_{tr} \frac{\partial T}{\partial n}\bigg|_w + \kappa_v \frac{\partial T_v}{\partial n}\bigg|_w}_{\text{Conductive Flux } q_{cond}} + \underbrace{\sum_{s \in \mathcal{S}} \rho_w D_{s,w} \frac{\partial Y_s}{\partial n}\bigg|_w h_s(T_w, T_{vw})}_{\text{Diffusive Chemical Flux } q_{diff}}$$

1. **Ideal Non-Catalytic Wall (NCW):**
   The wall is chemically inert ($\dot{w}_{s,w} = 0$). No surface recombination occurs:

$$\frac{\partial Y_s}{\partial n}\bigg|_w = 0 \quad \forall s \in \mathcal{S}$$

Consequently, $q_{diff} = 0$, and the wall heat transfer consists purely of thermal conduction:

$$q_{w,NCW} = \kappa_{tr} \frac{\partial T}{\partial n}\bigg|_w + \kappa_v \frac{\partial T_v}{\partial n}\bigg|_w$$

2. **Fully Catalytic Wall (FCW):**
   The surface catalyzes atomic recombination infinitely fast ($\gamma_s \to 1$), forcing the gas composition at the wall to reach local chemical equilibrium at the cold wall temperature $T_w$:

$$Y_s\big|_w = Y_s^*(p_w, T_w) \approx \begin{cases} 0 & \text{for } s \in \{\text{N}, \text{O}, \text{NO}\} \\ Y_{\text{N}_2,\infty}, Y_{\text{O}_2,\infty} & \text{for } s \in \{\text{N}_2, \text{O}_2\} \end{cases}$$

This creates the maximum possible concentration gradient $\frac{\partial Y_s}{\partial n}\big|_w$ for atomic species diffusing toward the wall, maximizing $q_{diff}$ and releasing the full formation enthalpy $\Delta h_{f,\text{N}}^0, \Delta h_{f,\text{O}}^0$ directly into the wall surface. 3. **Finite-Rate Catalytic Wall (Goulard's Recombination Model, 1958):**
From kinetic theory (Hertz-Knudsen effusion flux), the mass flux of atomic species $s \in \{\text{N}, \text{O}\}$ impinging on the wall per unit area and time is $j_{s,\text{imp}} = \frac{1}{4} \rho_w Y_{s,w} \bar{c}_{s,w} = \rho_w Y_{s,w} \sqrt{\frac{R_u T_w}{2\pi M_s}}$. Defining **Goulard's catalytic recombination efficiency** $\gamma_s \in [0, 1]$ as the probability that an impinging atom $s$ recombines on the surface ($\text{N} + \text{N}_{ads} \to \text{N}_2$, $\text{O} + \text{O}_{ads} \to \text{O}_2$), the heterogeneous catalytic sink rate for atomic species $s$ is:

$$\dot{w}_{s,w} = -k_{w,s} \rho_w Y_{s,w} \quad \text{where } k_{w,s} = \frac{2 \gamma_s}{2 - \gamma_s} \sqrt{\frac{R_u T_w}{2\pi M_s}} \quad \left(\text{or } k_{w,s} = \gamma_s \sqrt{\frac{R_u T_w}{2\pi M_s}} \text{ for } \gamma_s \ll 1\right)$$

(Here, the factor $\frac{2\gamma_s}{2-\gamma_s}$ is the exact Motz-Wise correction for Maxwellian velocity distortion near high-catalytic walls, reducing to Goulard's classic $\gamma_s$ for $\gamma_s \ll 1$). By elemental mass conservation at the surface, every recombining N or O atom produces an equal mass of $\text{N}_2$ or $\text{O}_2$:

$$\dot{w}_{\text{N}_2,w} = -\dot{w}_{\text{N},w} = +k_{w,\text{N}} \rho_w Y_{\text{N},w}, \qquad \dot{w}_{\text{O}_2,w} = -\dot{w}_{\text{O},w} = +k_{w,\text{O}} \rho_w Y_{\text{O},w}$$

Substituting into the Robin boundary condition $\rho_w D_{s,w} \frac{\partial Y_s}{\partial n}\big|_w = -\dot{w}_{s,w}$ yields:

$$\frac{\partial Y_s}{\partial n}\bigg|_w = \frac{k_{w,s}}{D_{s,w}} Y_{s,w}, \quad s \in \{\text{N}, \text{O}\}$$

Evaluating the diffusive chemical heat flux term $\sum_{s} \rho_w D_{s,w} \frac{\partial Y_s}{\partial n}\big|_w h_s(T_w)$ and noting that at low $T_w$, $h_{\text{N}}(T_w) - h_{\text{N}_2}(T_w) \approx \Delta h_{f,\text{N}}^0$ and $h_{\text{O}}(T_w) - h_{\text{O}_2}(T_w) \approx \Delta h_{f,\text{O}}^0$, the total wall heat flux is directly elevated by surface catalytic recombination:

$$q_w = \kappa_{tr} \frac{\partial T}{\partial n}\bigg|_w + \kappa_v \frac{\partial T_v}{\partial n}\bigg|_w + \rho_w k_{w,\text{N}} Y_{\text{N},w} \Delta h_{f,\text{N}}^0 + \rho_w k_{w,\text{O}} Y_{\text{O},w} \Delta h_{f,\text{O}}^0$$

Goulard (1958) showed that for a stagnation boundary layer with characteristic diffusion velocity $u_D \sim \frac{\rho_e \mu_e}{\rho_w} \sqrt{\beta} \, Sc^{-2/3}$, the ratio of chemical heat transfer varies smoothly with the surface Damköhler number $\phi_s = k_{w,s} / u_D$ as $\frac{\phi_s}{1 + \phi_s}$, bridging the non-catalytic ($\gamma_s = 0 \implies \phi_s = 0$) and fully catalytic ($\gamma_s = 1 \implies \phi_s \to \infty$) limits.

---

### 5. Executable Python Simulation Script

The following self-contained Python script implements the 1D Euler + Park (1993) 17-reaction two-temperature post-shock relaxation equations for $M_\infty = 14.5$ at $H = 65\text{ km}$. It computes the exact frozen Rankine-Hugoniot jump conditions, integrates the coupled stiff ODE system ($\frac{dY_s}{dx}, \frac{de_v}{dx}, \frac{du}{dx}, \frac{dT}{dx}$) over $x \in [0, 0.20]\text{ m}$ using `scipy.integrate.solve_ivp(method='Radau')`, and verifies strict elemental and total mass conservation.

```python
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

# ==============================================================================
# 1. PHYSICAL & THERMOCHEMICAL CONSTANTS (5-SPECIES AIR: N2, O2, NO, N, O)
# ==============================================================================
R_U = 8.314462618          # Universal gas constant [J/(mol*K)]
N_A = 6.02214076e23        # Avogadro's number [1/mol]
K_B = 1.380649e-23         # Boltzmann constant [J/K]
H_PLANCK = 6.62607015e-34  # Planck constant [J*s]
P_ATM = 101325.0           # Standard atmospheric pressure [Pa]

# Species indexing: 0: N2, 1: O2, 2: NO, 3: N, 4: O
SPECIES = ['N2', 'O2', 'NO', 'N', 'O']
N_SPEC = 5
MOL_INDICES = [0, 1, 2]    # Diatomic molecules with vibrational modes

# Molar masses [kg/mol]
M_S = np.array([28.0134e-3, 31.9988e-3, 30.0061e-3, 14.0067e-3, 15.9994e-3])
# Specific gas constants R_s = R_u / M_s [J/(kg*K)]
R_S = R_U / M_S

# Characteristic vibrational temperatures Theta_{v,s} [K] (for N2, O2, NO)
THETA_V = np.array([3395.0, 2239.0, 2817.0, 0.0, 0.0])

# Characteristic rotational temperatures Theta_{rot,s} [K] & symmetry factors
THETA_ROT = np.array([2.88, 2.08, 2.45, 0.0, 0.0])
SIGMA_SYM = np.array([2.0, 2.0, 1.0, 1.0, 1.0])

# Ground-state electronic degeneracy g_{0,s}
G_EL0 = np.array([1.0, 3.0, 4.0, 4.0, 9.0])

# Standard enthalpy of formation at 0 K [J/kg]
# Dissociation energies: D0(N2)=9.759 eV, D0(O2)=5.115 eV, D0(NO)=6.496 eV
DH_F0 = np.array([
    0.0,
    0.0,
    2.996123e6,   # NO: +89.90 kJ/mol
    3.362169e7,   # N:  +470.93 kJ/mol
    1.542514e7    # O:  +246.79 kJ/mol
])

# Translational-rotational specific heat at constant volume c_{v,tr-rot,s} [J/(kg*K)]
# 5/2 R_s for diatomic (N2, O2, NO), 3/2 R_s for monatomic (N, O)
CV_TR = np.array([2.5, 2.5, 2.5, 1.5, 1.5]) * R_S
CP_TR = CV_TR + R_S

# ==============================================================================
# 2. THERMODYNAMIC & VIBRATIONAL ENERGY FUNCTIONS
# ==============================================================================
def calc_ev_species(T_v):
    """Specific vibrational energy e_{v,s}(T_v) [J/kg] for all 5 species."""
    ev = np.zeros(N_SPEC)
    T_v_safe = max(T_v, 50.0)
    for i in MOL_INDICES:
        x = min(THETA_V[i] / T_v_safe, 500.0)
        ev[i] = R_S[i] * THETA_V[i] / (np.exp(x) - 1.0)
    return ev

def calc_cv_vib_species(T_v):
    """Vibrational specific heat d(e_{v,s})/dT_v [J/(kg*K)] for all 5 species."""
    cv_v = np.zeros(N_SPEC)
    T_v_safe = max(T_v, 50.0)
    for i in MOL_INDICES:
        x = min(THETA_V[i] / T_v_safe, 250.0)
        ex = np.exp(x)
        cv_v[i] = R_S[i] * (x**2) * ex / ((ex - 1.0)**2)
    return cv_v

def solve_Tv_from_ev(ev_mix, Y):
    """Invert mixture vibrational energy e_v = sum_{s in M} Y_s e_{v,s}(T_v) for T_v."""
    if ev_mix <= 1e-6:
        return 50.0
    def res(Tv):
        return np.dot(Y, calc_ev_species(Tv)) - ev_mix
    return brentq(res, 50.0, 60000.0, xtol=1e-6)

# ==============================================================================
# 3. STATISTICAL MECHANICS EQUILIBRIUM CONSTANTS K_c(T)
# ==============================================================================
def calc_partition_functions_per_vol(T):
    """
    Computes (Q_s(V,T) / V) / N_A [mol/m^3] and zero-point molar energy E0_s [J/mol]
    from statistical mechanics partition functions.
    """
    T_safe = max(T, 200.0)
    Q_vol_mol = np.zeros(N_SPEC)
    for s in range(N_SPEC):
        m_s = M_S[s] / N_A
        q_tr = ((2.0 * np.pi * m_s * K_B * T_safe) / (H_PLANCK**2))**1.5
        if s in MOL_INDICES:
            q_rot = T_safe / (SIGMA_SYM[s] * THETA_ROT[s])
            q_vib = 1.0 / (1.0 - np.exp(-THETA_V[s] / T_safe))
        else:
            q_rot = 1.0
            q_vib = 1.0
        q_el = G_EL0[s]
        Q_vol_mol[s] = (q_tr * q_rot * q_vib * q_el) / N_A
    return Q_vol_mol

# ==============================================================================
# 4. PARK (1993) 17-REACTION FINITE-RATE KINETIC MECHANISM
# ==============================================================================
# Reaction table: (reactant_indices, product_indices, C_f [m^3/(mol*s) or cm^3->m^3], eta, Theta_d [K], is_dissociation)
# Note: Park (1993) C_f values are converted from cm^3/(mol*s) to m^3/(mol*s) by multiplying by 1e-6.
PARK_93_REACTIONS = []

# 1-5: N2 + M <=> 2N + M (Theta_d = 113200 K, eta = -1.60)
# C_f = 7.0e21 cm^3/(mol*s) for M in {N2, O2, NO}, 3.0e22 cm^3/(mol*s) for M in {N, O}
C_N2_M = [7.0e15, 7.0e15, 7.0e15, 3.0e16, 3.0e16]
for m in range(N_SPEC):
    PARK_93_REACTIONS.append(([0, m], [3, 3, m], C_N2_M[m], -1.60, 113200.0, True))

# 6-10: O2 + M <=> 2O + M (Theta_d = 59500 K, eta = -1.50)
# C_f = 2.0e21 cm^3/(mol*s) for M in {N2, O2, NO}, 1.0e22 cm^3/(mol*s) for M in {N, O}
C_O2_M = [2.0e15, 2.0e15, 2.0e15, 1.0e16, 1.0e16]
for m in range(N_SPEC):
    PARK_93_REACTIONS.append(([1, m], [4, 4, m], C_O2_M[m], -1.50, 59500.0, True))

# 11-15: NO + M <=> N + O + M (Theta_d = 75500 K, eta = 0.00)
# C_f = 5.0e15 cm^3/(mol*s) for M in {N2, O2}, 1.1e17 cm^3/(mol*s) for M in {NO, N, O}
C_NO_M = [5.0e9, 5.0e9, 1.1e11, 1.1e11, 1.1e11]
for m in range(N_SPEC):
    PARK_93_REACTIONS.append(([2, m], [3, 4, m], C_NO_M[m], 0.00, 75500.0, True))

# 16: N2 + O <=> NO + N (Zeldovich Exchange 1: C_f = 6.4e17 cm^3/(mol*s), eta = -1.00, Theta_d = 38400 K)
PARK_93_REACTIONS.append(([0, 4], [2, 3], 6.4e11, -1.00, 38400.0, False))

# 17: NO + O <=> O2 + N (Zeldovich Exchange 2: C_f = 8.4e12 cm^3/(mol*s), eta = 0.00, Theta_d = 19450 K)
PARK_93_REACTIONS.append(([2, 4], [1, 3], 8.4e6, 0.00, 19450.0, False))

def compute_chemical_source_terms(rho, T, T_v, Y):
    """
    Computes species mass production rates omega_dot_s [kg/(m^3*s)]
    across all 17 Park (1993) elementary reactions.
    """
    T_safe = max(T, 200.0)
    T_v_safe = max(T_v, 200.0)
    # Park two-temperature controlling temperature T_a = T^q * T_v^(1-q) with q = 0.5
    T_a_diss = np.sqrt(T_safe * T_v_safe)

    # Molar concentrations [mol/m^3]
    C_s = np.maximum(rho * Y / M_S, 0.0)

    # Partition functions for equilibrium constants K_c(T)
    Q_vol_mol = calc_partition_functions_per_vol(T_safe)
    E0_mol = DH_F0 * M_S  # Molar zero-point formation energy [J/mol]

    omega_mol = np.zeros(N_SPEC)  # [mol/(m^3*s)]

    for reacts, prods, C_f, eta, Theta_d, is_diss in PARK_93_REACTIONS:
        T_ctrl = T_a_diss if is_diss else T_safe
        k_f = C_f * (T_ctrl**eta) * np.exp(-Theta_d / T_ctrl)

        # Equilibrium constant K_c(T) evaluated at translational temperature T
        dE0 = sum(E0_mol[p] for p in prods) - sum(E0_mol[r] for r in reacts)
        q_ratio = 1.0
        for p in prods:
            q_ratio *= Q_vol_mol[p]
        for r in reacts:
            q_ratio /= Q_vol_mol[r]
        K_c = q_ratio * np.exp(-min(max(dE0 / (R_U * T_safe), -500.0), 500.0))
        K_c = max(K_c, 1e-100)

        # Backward rate evaluated strictly at T
        k_b = k_f / K_c

        # Law of Mass Action
        rate_f = k_f
        for r in reacts:
            rate_f *= C_s[r]
        rate_b = k_b
        for p in prods:
            rate_b *= C_s[p]

        net_rate = rate_f - rate_b
        for r in reacts:
            omega_mol[r] -= net_rate
        for p in prods:
            omega_mol[p] += net_rate

    return omega_mol * M_S  # [kg/(m^3*s)]

# ==============================================================================
# 5. VIBRATIONAL-TRANSLATIONAL RELAXATION (LANDAU-TELLER + MILLIKAN-WHITE + PARK)
# ==============================================================================
def compute_Q_VT(rho, T, T_v, Y):
    """
    Computes the vibrational-translational energy exchange source term Q_VT [W/m^3]
    using Landau-Teller relaxation, Millikan-White collision times, and Park's
    high-temperature limiting cross-section correction.
    """
    T_safe = max(T, 200.0)
    T_v_safe = max(T_v, 200.0)

    # Molar concentrations and mole fractions
    C_s = np.maximum(rho * Y / M_S, 1e-30)
    C_tot = np.sum(C_s)
    X_s = C_s / C_tot

    # Mixture pressure in atmospheres
    p_pa = C_tot * R_U * T_safe
    p_atm = p_pa / P_ATM

    # Total number density [1/m^3]
    n_tot = C_tot * N_A

    # Park high-temperature limiting vibrational cross-section [m^2]
    sigma_v = 1.0e-21 * ((50000.0 / T_safe)**2)

    ev_T = calc_ev_species(T_safe)
    ev_Tv = calc_ev_species(T_v_safe)

    Q_vt = 0.0
    for s in MOL_INDICES:
        if Y[s] <= 1e-15:
            continue
        # Millikan-White harmonic average across all collision partners r
        inv_tau_mw = 0.0
        for r in range(N_SPEC):
            # Reduced molecular weight in g/mol
            mu_sr = (M_S[s] * 1e3 * M_S[r] * 1e3) / ((M_S[s] + M_S[r]) * 1e3)
            A_sr = 1.16e-3 * (mu_sr**0.5) * (THETA_V[s]**(4.0 / 3.0))
            B_sr = 0.015 * (mu_sr**0.25)
            exponent = min(max(A_sr * (T_safe**(-1.0 / 3.0) - B_sr) - 18.42, -100.0), 100.0)
            tau_sr_mw = np.exp(exponent) / p_atm
            inv_tau_mw += X_s[r] / tau_sr_mw

        tau_s_mw = 1.0 / inv_tau_mw

        # Park high-temperature correction tau_s^P
        c_bar_s = np.sqrt(8.0 * R_U * T_safe / (np.pi * M_S[s]))
        tau_s_park = 1.0 / (n_tot * sigma_v * c_bar_s)

        tau_s_total = tau_s_mw + tau_s_park
        Q_vt += (rho * Y[s]) * (ev_T[s] - ev_Tv[s]) / tau_s_total

    return Q_vt

# ==============================================================================
# 6. 1D POST-SHOCK RELAXATION ODE SYSTEM
# ==============================================================================
def run_post_shock_simulation():
    # Free-stream specifications: M_inf = 14.5, H = 65 km
    M_inf = 14.5
    P_inf = 10.93          # [Pa]
    T_inf = 233.3          # [K]
    rho_inf = 1.63e-4      # [kg/m^3]

    # Standard dry air mass fractions (76.7% N2, 23.3% O2 by mass)
    Y_inf = np.array([0.767, 0.233, 0.0, 0.0, 0.0])
    R_mix_inf = np.dot(Y_inf, R_S)
    gamma_f = 1.4

    # Free-stream velocity from M_inf and speed of sound a_inf = sqrt(gamma_f * R_mix * T_inf)
    a_inf = np.sqrt(gamma_f * R_mix_inf * T_inf)
    u_inf = M_inf * a_inf

    # Exact Rankine-Hugoniot Frozen Shock Jump Conditions (State 2,f at x = 0+)
    rho_ratio_f = ((gamma_f + 1.0) * M_inf**2) / ((gamma_f - 1.0) * M_inf**2 + 2.0)
    p_ratio_f = 1.0 + (2.0 * gamma_f / (gamma_f + 1.0)) * (M_inf**2 - 1.0)
    T_ratio_f = p_ratio_f / rho_ratio_f

    rho_2f = rho_inf * rho_ratio_f
    u_2f = u_inf / rho_ratio_f
    T_2f = T_inf * T_ratio_f
    Tv_2f = T_inf
    Y_2f = Y_inf.copy()
    ev_2f = np.dot(Y_2f, calc_ev_species(Tv_2f))

    # Conserved mass flux m_dot = rho * u
    m_dot = rho_2f * u_2f

    # Initial elemental mass fractions (N and O elemental conservation baseline)
    elem_N_init = Y_inf[0] + (M_S[3] / M_S[2]) * Y_inf[2] + Y_inf[3]
    elem_O_init = Y_inf[1] + (M_S[4] / M_S[2]) * Y_inf[2] + Y_inf[4]
    N_to_O_ratio_init = elem_N_init / elem_O_init

    # State vector: y = [Y_N2, Y_O2, Y_NO, Y_N, Y_O, e_v, u, T]
    y0 = np.concatenate([Y_2f, [ev_2f, u_2f, T_2f]])

    def rhs_relaxation(x, y):
        Y = y[0:5]
        ev_mix = y[5]
        u = y[6]
        T = y[7]

        rho = m_dot / u
        T_v = solve_Tv_from_ev(ev_mix, Y)

        # 1. Species continuity: dY_s / dx = omega_dot_s / m_dot
        omega_dot = compute_chemical_source_terms(rho, T, T_v, Y)
        dY_dx = omega_dot / m_dot

        # 2. Vibrational energy conservation: d(e_v)/dx = (Q_VT + Q_chem_v) / m_dot
        Q_vt = compute_Q_VT(rho, T, T_v, Y)
        ev_s = calc_ev_species(T_v)
        Q_chem_v = np.dot(omega_dot, ev_s)
        dev_dx = (Q_vt + Q_chem_v) / m_dot

        # 3. Coupled Momentum & Total Enthalpy ODEs for du/dx and dT/dx:
        # Momentum: m_dot * du/dx + dp/dx = 0
        # where p = rho * R_mix * T = (m_dot / u) * R_mix * T
        # => dp/dx = -(p / u) * du/dx + (p / T) * dT/dx + rho * T * sum(R_s * dY_s/dx)
        # Total Enthalpy: cp_tr_mix * dT/dx + dev_dx + sum((h_tr_s + dh_f0_s) * dY_s/dx) + u * du/dx = 0
        R_mix = np.dot(Y, R_S)
        cp_tr_mix = np.dot(Y, CP_TR)
        p = rho * R_mix * T

        h_tr_f_s = CP_TR * T + DH_F0
        S_Y = np.dot(R_S, dY_dx)
        S_h = dev_dx + np.dot(h_tr_f_s, dY_dx)

        # From enthalpy: dT/dx = -(S_h + u * du/dx) / cp_tr_mix
        # Substitute into momentum:
        # [ m_dot - p/u - (p * u) / (T * cp_tr_mix) ] * du/dx = (p / (T * cp_tr_mix)) * S_h - rho * T * S_Y
        coeff_du = m_dot - (p / u) - (p * u) / (T * cp_tr_mix)
        rhs_du = (p / (T * cp_tr_mix)) * S_h - rho * T * S_Y

        du_dx = rhs_du / coeff_du
        dT_dx = -(S_h + u * du_dx) / cp_tr_mix

        return np.concatenate([dY_dx, [dev_dx, du_dx, dT_dx]])

    # Integrate downstream from x = 0 to x = 0.20 m using stiff Radau solver
    x_eval = np.array([0.0, 1.0e-4, 5.0e-4, 2.0e-3, 1.0e-2, 5.0e-2, 0.10, 0.20])
    sol = solve_ivp(
        rhs_relaxation,
        t_span=(0.0, 0.20),
        y0=y0,
        method='Radau',
        t_eval=x_eval,
        rtol=1e-8,
        atol=1e-10
    )

    assert sol.success, f"ODE integration failed: {sol.message}"

    print("=" * 86)
    print("HYPERSONIC 1D POST-SHOCK RELAXATION VERIFICATION (M_inf = 14.5, H = 65 km)")
    print("=" * 86)
    print(f"Free-stream: u_inf = {u_inf:.2f} m/s, T_inf = {T_inf:.1f} K, P_inf = {P_inf:.2f} Pa")
    print(f"Frozen Jump: u_2f  = {u_2f:.2f} m/s, T_2f  = {T_2f:.1f} K, Tv_2f = {Tv_2f:.1f} K, rho_2f/rho_inf = {rho_ratio_f:.4f}")
    print("-" * 86)
    print(f"{'x [m]':>9} | {'T [K]':>8} | {'T_v [K]':>8} | {'Y_N2':>8} | {'Y_O2':>8} | {'Y_NO':>8} | {'Y_N':>8} | {'Y_O':>8}")
    print("-" * 86)

    violations = 0
    for i, x_val in enumerate(sol.t):
        y_col = sol.y[:, i]
        Y_curr = y_col[0:5]
        ev_curr = y_col[5]
        u_curr = y_col[6]
        T_curr = y_col[7]
        Tv_curr = solve_Tv_from_ev(ev_curr, Y_curr)

        # Verify total mass fraction conservation
        sum_Y = np.sum(Y_curr)
        if abs(sum_Y - 1.0) > 1e-6:
            violations += 1

        # Verify strict elemental N/O mass conservation
        elem_N = Y_curr[0] + (M_S[3] / M_S[2]) * Y_curr[2] + Y_curr[3]
        elem_O = Y_curr[1] + (M_S[4] / M_S[2]) * Y_curr[2] + Y_curr[4]
        if abs((elem_N / elem_O) - N_to_O_ratio_init) > 1e-6:
            violations += 1

        print(f"{x_val:9.5f} | {T_curr:8.1f} | {Tv_curr:8.1f} | "
              f"{Y_curr[0]:8.5f} | {Y_curr[1]:8.5f} | {Y_curr[2]:8.5f} | "
              f"{Y_curr[3]:8.5f} | {Y_curr[4]:8.5f}")

    print("-" * 86)
    final_Y = sol.y[0:5, -1]
    final_elem_N = final_Y[0] + (M_S[3] / M_S[2]) * final_Y[2] + final_Y[3]
    final_elem_O = final_Y[1] + (M_S[4] / M_S[2]) * final_Y[2] + final_Y[4]
    print(f"Final Mass Sum = {np.sum(final_Y):.8f} (Target: 1.00000000)")
    print(f"Final Elemental N/O Mass Ratio = {final_elem_N / final_elem_O:.8f} (Initial: {N_to_O_ratio_init:.8f})")
    assert violations == 0, f"Detected {violations} conservation violations!"
    print("PASSED: Hypersonic non-equilibrium relaxation verified, violations: 0")

if __name__ == "__main__":
    run_post_shock_simulation()

```

---

### 6. Citation Ledger

- **Park, C. (1990).** _Nonequilibrium Hypersonic Aerothermodynamics_. John Wiley & Sons, New York. ISBN: 978-0-471-51093-2.
- **Park, C. (1993).** "Review of chemical-kinetic problems of future NASA missions, I: Earth entries." _Journal of Thermophysics and Heat Transfer_, 7(3), 385–398. DOI: `10.2514/3.431`.
- **Millikan, R. C., & White, D. R. (1963).** "Systematics of vibrational relaxation." _The Journal of Chemical Physics_, 39(12), 3209–3213. DOI: `10.1063/1.1734182`.
- **Goulard, R. (1958).** "On catalytic recombination rates in hypersonic stagnation heat transfer." _Jet Propulsion_, 28(11), 737–745. DOI: `10.2514/8.7444`.
- **Landau, L., & Teller, E. (1936).** "Zur Theorie der Schalldispersion." _Physikalische Zeitschrift der Sowjetunion_, 10, 34–43.
- **Gnoffo, P. A., Gupta, R. N., & Shinn, J. L. (1989).** "Conservation equations and physical models for hypersonic air flows in thermal and chemical nonequilibrium." _NASA Technical Paper 2867_.
