/**
 * ============================================================
 * SGPP — CONTROLADOR DO TUTORIAL INTERATIVO
 * Gerencia a navegação entre passos, animações suaves e persistência
 * ============================================================
 */

(function () {
    let passoAtual = 1;
    const TOTAL_PASSOS = 6;
    let overlay = null;
    let progressLine = null;
    let btnPrev = null;
    let btnNext = null;
    let btnFinish = null;

    function initTutorial() {
        overlay = document.getElementById('sgppTutorialOverlay');
        progressLine = document.getElementById('tutorialProgressLine');
        btnPrev = document.getElementById('btnTutorialPrev');
        btnNext = document.getElementById('btnTutorialNext');
        btnFinish = document.getElementById('btnTutorialFinish');

        if (!overlay) return;

        // Fecha ao pressionar a tecla ESC, navega com setas
        document.addEventListener('keydown', function (e) {
            if (!overlay.classList.contains('active')) return;

            if (e.key === 'Escape') {
                fecharTutorial();
            } else if (e.key === 'ArrowRight') {
                proximoPasso();
            } else if (e.key === 'ArrowLeft') {
                passoAnterior();
            }
        });

        // Fecha ao clicar fora da janela de diálogo
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                fecharTutorial();
            }
        });

        // Verifica se a página solicitou abertura automática
        if (window.SGPP_AUTO_TUTORIAL === true || window.location.search.includes('tutorial=1') || window.location.search.includes('tutorial=true')) {
            setTimeout(function () {
                abrirTutorial(1);
            }, 450); // Aguarda renderização da página para transição fluida
        }
    }

    function atualizarInterface() {
        if (!overlay) return;

        // Atualiza os slides de conteúdo
        const steps = overlay.querySelectorAll('.sgpp-tutorial-step-content');
        steps.forEach((stepEl) => {
            const stepNum = parseInt(stepEl.getAttribute('data-step'), 10);
            if (stepNum === passoAtual) {
                stepEl.classList.add('active');
            } else {
                stepEl.classList.remove('active');
            }
        });

        // Atualiza os botões do stepper no cabeçalho
        const stepperItems = overlay.querySelectorAll('.sgpp-tutorial-step-item');
        stepperItems.forEach((item, index) => {
            const stepIndex = index + 1;
            item.classList.remove('active', 'completed');
            if (stepIndex === passoAtual) {
                item.classList.add('active');
            } else if (stepIndex < passoAtual) {
                item.classList.add('completed');
            }
        });

        // Atualiza a barra de progresso horizontal
        if (progressLine) {
            const percentual = ((passoAtual - 1) / (TOTAL_PASSOS - 1)) * 100;
            progressLine.style.width = percentual + '%';
        }

        // Atualiza os botões de ação do rodapé
        if (btnPrev) {
            btnPrev.disabled = passoAtual === 1;
        }

        if (passoAtual === TOTAL_PASSOS) {
            if (btnNext) btnNext.classList.add('d-none');
            if (btnFinish) btnFinish.classList.remove('d-none');
        } else {
            if (btnNext) btnNext.classList.remove('d-none');
            if (btnFinish) btnFinish.classList.add('d-none');
        }

        // Rola o container do corpo suavemente para o topo se houver rolagem interna
        const bodyContainer = document.getElementById('tutorialBodyContainer');
        if (bodyContainer) {
            bodyContainer.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    window.abrirTutorial = function (passo = 1) {
        if (!overlay) initTutorial();
        if (!overlay) return;

        passoAtual = Math.max(1, Math.min(passo, TOTAL_PASSOS));
        atualizarInterface();

        overlay.classList.add('active');
        document.body.style.overflow = 'hidden'; // Evita rolagem da página de fundo
    };

    window.fecharTutorial = function () {
        if (!overlay) return;
        overlay.classList.remove('active');
        document.body.style.overflow = '';

        // Notifica o backend silenciosamente caso queira registrar
        fetch('/api/concluir_tutorial', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        }).catch(function (err) {
            console.log('Aviso ao registrar fechamento do tutorial:', err);
        });

        // Limpa parâmetro da URL de forma limpa sem recarregar a página
        if (window.history && window.history.replaceState && window.location.search.includes('tutorial=')) {
            const cleanUrl = window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
        }
    };

    window.proximoPasso = function () {
        if (passoAtual < TOTAL_PASSOS) {
            passoAtual++;
            atualizarInterface();
        } else {
            concluirTutorial();
        }
    };

    window.passoAnterior = function () {
        if (passoAtual > 1) {
            passoAtual--;
            atualizarInterface();
        }
    };

    window.irParaPasso = function (passo) {
        if (passo >= 1 && passo <= TOTAL_PASSOS) {
            passoAtual = passo;
            atualizarInterface();
        }
    };

    window.concluirTutorial = function () {
        fecharTutorial();

        // Feedback positivo e acolhedor (Toast amigável)
        const toast = document.createElement('div');
        toast.className = 'alert alert-success position-fixed shadow-lg d-flex align-items-center gap-2';
        toast.style.cssText = 'bottom: 24px; right: 24px; z-index: 99999; border-radius: 14px; padding: 16px 22px; font-weight: 600; animation: toastSlideIn 0.35s ease forwards;';
        toast.innerHTML = '<i class="bi bi-check-circle-fill fs-5 text-success"></i> <span>Excelente! Você já pode aproveitar o SGPP. Bom trabalho, Professor(a)!</span>';
        document.body.appendChild(toast);

        setTimeout(function () {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s ease';
            setTimeout(function () {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 500);
        }, 4000);
    };

    // Inicializa quando o DOM estiver pronto
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTutorial);
    } else {
        initTutorial();
    }
})();
