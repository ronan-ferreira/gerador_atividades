/* SGPP — utilitários de senha das telas de autenticação */
(function () {
    // Mostrar / ocultar senha
    document.querySelectorAll('[data-toggle-pwd]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var inp = document.getElementById(btn.dataset.togglePwd);
            var mostrar = inp.type === 'password';
            inp.type = mostrar ? 'text' : 'password';
            btn.textContent = mostrar ? 'Ocultar' : 'Mostrar';
        });
    });

    function avaliar(v) {
        var regras = {
            len: v.length >= 8,
            upper: /[A-ZÀ-Ý]/.test(v),
            lower: /[a-zà-ý]/.test(v),
            num: /[0-9]/.test(v),
            spec: /[^A-Za-zÀ-ÿ0-9\s]/.test(v)
        };
        var repetida = v.length >= 8 && new Set(v).size === 1;
        var pontos = Object.keys(regras).filter(function (k) { return regras[k]; }).length;
        return { regras: regras, pontos: pontos, valida: pontos === 5 && !repetida, repetida: repetida };
    }

    var pwd = document.querySelector('[data-pwd-strength]');
    if (!pwd) return;

    var confirmar = document.getElementById(pwd.dataset.confirm);
    var bar = document.getElementById('pwd-bar');
    var label = document.getElementById('pwd-label');
    var hint = document.getElementById('pwd-match');
    var erroBox = document.getElementById('form-error');
    var itens = document.querySelectorAll('#pwd-rules [data-rule]');

    function atualizar() {
        var v = pwd.value;
        var r = avaliar(v);

        itens.forEach(function (li) {
            li.classList.toggle('ok', !!r.regras[li.dataset.rule]);
        });

        var largura = '0', cor = '#e2e8f0', texto = '';
        if (v.length) {
            if (!r.regras.len || r.pontos <= 3 || r.repetida) { largura = '33%'; cor = '#dc2626'; texto = 'Fraca'; }
            else if (r.pontos === 4) { largura = '66%'; cor = '#d97706'; texto = 'Média'; }
            else { largura = '100%'; cor = '#15803d'; texto = 'Forte'; }
        }
        bar.style.width = largura;
        bar.style.backgroundColor = cor;
        label.textContent = texto;
        label.style.color = v.length ? cor : '';

        if (confirmar && confirmar.value) conferir();
    }

    function conferir() {
        if (!confirmar || !hint) return;
        if (!confirmar.value) {
            hint.textContent = '';
            confirmar.classList.remove('is-invalid');
            return;
        }
        var igual = confirmar.value === pwd.value;
        hint.textContent = igual ? 'As senhas coincidem.' : 'As senhas não coincidem.';
        hint.style.color = igual ? '#15803d' : '#dc2626';
        confirmar.classList.toggle('is-invalid', !igual);
    }

    function mostrarErro(msg, campo) {
        if (erroBox) {
            erroBox.textContent = msg;
            erroBox.hidden = false;
        }
        if (campo) campo.focus();
    }

    pwd.addEventListener('input', atualizar);
    if (confirmar) confirmar.addEventListener('input', conferir);

    if (pwd.form) {
        pwd.form.addEventListener('submit', function (e) {
            var v = pwd.value;
            if (v.length < 8) {
                e.preventDefault();
                return mostrarErro('A senha deve ter no mínimo 8 caracteres.', pwd);
            }
            if (!avaliar(v).valida) {
                e.preventDefault();
                return mostrarErro('Senha fraca. Use letra maiúscula, minúscula, número e caractere especial.', pwd);
            }
            if (confirmar && confirmar.value !== v) {
                e.preventDefault();
                return mostrarErro('A confirmação não confere com a senha digitada.', confirmar);
            }
        });
    }
})();
