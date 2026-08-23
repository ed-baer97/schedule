const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт']

const ROWS: Array<Array<{ t: string; k: string } | null>> = [
  [
    { t: 'Матем', k: 'a' },
    { t: 'Русск', k: 'b' },
    { t: 'Мир', k: 'c' },
    { t: 'Англ', k: 'd' },
    { t: 'Физ-ра', k: 'e' },
  ],
  [
    { t: 'Русск', k: 'b' },
    { t: 'Матем', k: 'a' },
    { t: 'Труд', k: 'c' },
    { t: 'Матем', k: 'a' },
    { t: 'Музыка', k: 'd' },
  ],
  [
    { t: 'Чтение', k: 'b' },
    { t: 'Мир', k: 'c' },
    { t: 'Матем', k: 'a' },
    { t: 'Русск', k: 'b' },
    { t: 'ИЗО', k: 'e' },
  ],
  [
    { t: 'Матем', k: 'a' },
    { t: 'Англ', k: 'd' },
    null,
    { t: 'Чтение', k: 'b' },
    { t: 'Мир', k: 'c' },
  ],
  [
    { t: 'История', k: 'd' },
    { t: 'Физ-ра', k: 'e' },
    { t: 'Русск', k: 'b' },
    { t: 'Матем', k: 'a' },
    { t: 'Техн', k: 'c' },
  ],
  [
    { t: 'Музыка', k: 'd' },
    { t: 'Чтение', k: 'b' },
    { t: 'Англ', k: 'd' },
    { t: 'ИЗО', k: 'e' },
    null,
  ],
  [
    { t: 'Мир', k: 'c' },
    null,
    { t: 'Матем', k: 'a' },
    { t: 'Физ-ра', k: 'e' },
    { t: 'Русск', k: 'b' },
  ],
]

export function LandingTimetable() {
  return (
    <div className="landing-tt">
      <span />
      {DAYS.map((d) => (
        <span key={d} className="landing-tt-h">
          {d}
        </span>
      ))}
      {ROWS.map((row, i) => (
        <span key={`r${i}`} className="landing-tt-row">
          <span className="landing-tt-n">{i + 1}</span>
          {row.map((cell, j) =>
            cell ? (
              <span key={`${i}-${j}`} className={`landing-chip landing-chip--${cell.k}`}>
                {cell.t}
              </span>
            ) : (
              <span key={`${i}-${j}`} className="landing-chip landing-chip--empty" />
            ),
          )}
        </span>
      ))}
    </div>
  )
}
